from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import forms
import json
import re

from django.db.models import Max, Min, Q
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from config.widgets import TeamMemberPickerWidget
from hr.teams.models import TeamMember, TeamMemberGradePeriod, TeamMemberRollPeriod

from .models import (
    Engagement,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    DivisionWorkArea,
    DivisionWorkAreaTeamAssignment,
    DivisionWorkAreaPeriod,
    EngagementSchedule,
    EngagementTeamAssignment,
    EngagementWorkArea,
    EngagementWorkAreaTeamAssignment,
    EngagementWorkAreaPeriod,
)


def _team_member_pks_assigned_to_engagement_division(division):
    if division is None:
        return set()
    return set(
        EngagementDivisionTeamAssignment.objects.filter(
            division=division,
        ).values_list("team_member_id", flat=True)
    )


def _team_member_pks_assigned_to_engagement(engagement):
    if engagement is None:
        return set()
    return set(
        EngagementTeamAssignment.objects.filter(
            engagement=engagement,
        ).values_list("team_member_id", flat=True)
    )


def _work_area_team_member_queryset_allowed_pks(allowed_ids, instance):
    pks = set(allowed_ids)
    if (
        instance
        and getattr(instance, "pk", None)
        and getattr(instance, "team_member_id", None)
    ):
        pks.add(instance.team_member_id)
    return (
        TeamMember.objects.filter(pk__in=pks).order_by("first_name", "last_name", "code")
        if pks
        else TeamMember.objects.none()
    )


def _team_member_earliest_roll_start_map(team_member_ids):
    rows = (
        TeamMemberRollPeriod.objects.filter(team_member_id__in=team_member_ids)
        .values("team_member_id")
        .annotate(earliest_from=Min("from_date"))
    )
    return {
        str(row["team_member_id"]): row["earliest_from"].isoformat()
        for row in rows
        if row["earliest_from"] is not None
    }


def _format_member_period_hints(periods_qs) -> str:
    parts = []
    for period in periods_qs.order_by("from_date", "id"):
        end_label = period.to_date.isoformat() if period.to_date else "Present"
        parts.append(f"{period.from_date.isoformat()} to {end_label}")
    return "; ".join(parts)


def _assignment_period_source(team_member):
    grade_qs = TeamMemberGradePeriod.objects.filter(team_member=team_member)
    if grade_qs.exists():
        return grade_qs, "role", "grade mapping"
    roll_qs = TeamMemberRollPeriod.objects.filter(team_member=team_member)
    return roll_qs, "on-roll", "roll"


def _date_range_fully_covered_by_periods(periods_qs, range_start, range_end) -> bool:
    periods = list(periods_qs.order_by("from_date", "id"))
    if not periods:
        return False

    cursor = range_start
    while cursor <= range_end:
        matched = None
        for period in periods:
            period_end = period.to_date
            if period.from_date <= cursor and (
                period_end is None or period_end >= cursor
            ):
                matched = period
                break
        if matched is None:
            return False
        segment_end = matched.to_date or range_end
        segment_end = min(segment_end, range_end)
        cursor = segment_end + timedelta(days=1)
    return True


def _team_member_planned_dates_within_assignment_periods(
    team_member, planned_start, planned_finish
) -> bool:
    if team_member is None or planned_start is None or planned_finish is None:
        return False
    periods_qs, _, _ = _assignment_period_source(team_member)
    return _date_range_fully_covered_by_periods(
        periods_qs, planned_start, planned_finish
    )


def _assignment_period_validation_error(team_member):
    periods_qs, period_kind, period_label = _assignment_period_source(team_member)
    if not periods_qs.exists():
        setup_hint = (
            "Add team grade mappings first."
            if period_label == "grade mapping"
            else "Add team roll dates first."
        )
        return (
            "team_member",
            f"Selected team member has no team {period_label} period. {setup_hint}",
        )
    return (
        "planned_start",
        (
            f"Assignment dates must fall within {period_kind} period(s) for this member "
            "(each day in the range must be covered). "
            f"Recorded periods: {_format_member_period_hints(periods_qs)}."
        ),
    )


def _engagement_select_label(engagement: Engagement) -> str:
    """Human-readable label for engagement dropdowns (value is still engagement pk)."""
    name = engagement.client.display_name
    fy = engagement.fiscal_year.fy_no
    svc = engagement.service.service_desc
    return f"{name} · {fy} · {svc}"


class EngagementModelChoiceField(forms.ModelChoiceField):
    """Uses readable labels; submitted value remains the engagement primary key."""

    def label_from_instance(self, obj):
        return _engagement_select_label(obj)


def _documentation_choice_label(item: EngagementDocumentation) -> str:
    names = ", ".join(
        c.classification_name
        for c in sorted(
            item.applicable_classifications.all(),
            key=lambda c: c.classification_name,
        )
    )
    return (
        f"{item.standard_document} "
        f"({item.get_document_stage_display()} - {names})"
    )


def filter_engagement_documentation_by_client_classification(
    queryset,
    client,
    *,
    include_documentation_pk=None,
):
    """Keep setup documentation rows whose Applicable To includes the client's classification."""
    classification = getattr(client, "classification", None)
    if classification is None:
        return queryset.none()
    q = Q(applicable_classifications=classification)
    if include_documentation_pk:
        q |= Q(pk=include_documentation_pk)
    return queryset.filter(q).distinct()


def _format_fee_amount_display(value) -> str:
    if value is None or value == "":
        return ""
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return f"{int(d):,}"
    text = f"{d:,.2f}"
    if text.endswith(".00"):
        return text[:-3]
    return text.rstrip("0").rstrip(".")


class EngagementForm(forms.ModelForm):
    fee_amount = forms.CharField(
        required=False,
        label=Engagement._meta.get_field("fee_amount").verbose_name,
        widget=forms.TextInput(
            attrs={
                "class": "input-medium",
                "inputmode": "decimal",
                "autocomplete": "off",
                "data-amount-formatted": "1",
            }
        ),
    )

    class Meta:
        model = Engagement
        fields = [
            "client",
            "fiscal_year",
            "service",
            "fee_amount",
            "engagement_mail_id",
            "additional_mail_ids",
        ]
        widgets = {
            "client": forms.Select(attrs={"class": "input-medium"}),
            "fiscal_year": forms.Select(attrs={"class": "input-compact"}),
            "service": forms.Select(attrs={"class": "input-medium"}),
            "engagement_mail_id": forms.EmailInput(attrs={"class": "input-long"}),
            "additional_mail_ids": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 3,
                    "placeholder": "Comma/newline separated additional email IDs",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.order_by(
            "client_name", "client_code"
        )
        self.fields["fiscal_year"].queryset = self.fields[
            "fiscal_year"
        ].queryset.order_by("-fy_no")
        self.fields["service"].queryset = self.fields["service"].queryset.order_by(
            "service_desc", "service_code"
        )
        if (
            not self.is_bound
            and self.instance
            and getattr(self.instance, "pk", None)
            and not (self.instance.engagement_mail_id or "").strip()
            and getattr(self.instance, "client", None) is not None
        ):
            self.initial.setdefault(
                "engagement_mail_id", (self.instance.client.mail_id or "").strip()
            )
        if (
            not self.is_bound
            and self.instance
            and getattr(self.instance, "pk", None)
            and not (self.instance.additional_mail_ids or "").strip()
            and getattr(self.instance, "client", None) is not None
            and (self.instance.client.additional_mail_ids or "").strip()
        ):
            self.initial.setdefault(
                "additional_mail_ids",
                (self.instance.client.additional_mail_ids or "").strip(),
            )
        fee_val = self.initial.get("fee_amount")
        if fee_val is None and self.instance and getattr(self.instance, "pk", None):
            fee_val = self.instance.fee_amount
        if fee_val not in (None, ""):
            self.initial["fee_amount"] = _format_fee_amount_display(fee_val)

    def clean_fee_amount(self):
        raw = self.cleaned_data.get("fee_amount")
        if raw is None:
            return None
        if isinstance(raw, Decimal):
            return raw if raw >= 0 else None
        text = str(raw).replace(",", "").strip()
        if not text:
            return None
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError("Enter a valid fee amount.") from exc
        if amount < 0:
            raise ValidationError("Fee amount cannot be negative.")
        return amount

    @staticmethod
    def _split_mail_ids(raw: str):
        text = (raw or "").strip()
        if not text:
            return []
        parts = [p.strip() for p in re.split(r"[,\n;]+", text) if p.strip()]
        return parts

    def clean_engagement_mail_id(self):
        mail_id = (self.cleaned_data.get("engagement_mail_id") or "").strip()
        client = self.cleaned_data.get("client") or getattr(self.instance, "client", None)
        if not mail_id and client is not None:
            mail_id = (client.mail_id or "").strip()
        if mail_id:
            validate_email(mail_id)
        return mail_id

    def clean_additional_mail_ids(self):
        raw = self.cleaned_data.get("additional_mail_ids") or ""
        entries = self._split_mail_ids(raw)
        client = self.cleaned_data.get("client") or getattr(self.instance, "client", None)
        if not entries and client is not None:
            entries = self._split_mail_ids(client.additional_mail_ids or "")
        invalid = []
        for item in entries:
            try:
                validate_email(item)
            except ValidationError:
                invalid.append(item)
        if invalid:
            raise forms.ValidationError(
                "Invalid email(s): " + ", ".join(invalid[:5])
            )
        return ", ".join(entries)

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        fiscal_year = cleaned_data.get("fiscal_year")
        service = cleaned_data.get("service")
        if client and fiscal_year and service:
            qs = Engagement.objects.filter(
                client=client,
                fiscal_year=fiscal_year,
                service=service,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "An engagement already exists for this client, FY, and service."
                )
        return cleaned_data


class EngagementScheduleForm(forms.ModelForm):
    class Meta:
        model = EngagementSchedule
        fields = ["planned_start", "planned_finish", "actual_start", "actual_finish"]
        widgets = {
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        actual_start = cleaned_data.get("actual_start")
        actual_finish = cleaned_data.get("actual_finish")

        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )

        if actual_start and actual_finish and actual_finish < actual_start:
            self.add_error(
                "actual_finish",
                "Actual finish cannot be before actual start.",
            )

        return cleaned_data


class EngagementTeamAssignmentForm(forms.ModelForm):
    class Meta:
        model = EngagementTeamAssignment
        fields = ["team_member", "planned_start", "planned_finish"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, engagement=None, **kwargs):
        self.engagement = engagement
        super().__init__(*args, **kwargs)
        self.fields["team_member"].queryset = TeamMember.objects.order_by(
            "first_name", "last_name", "code"
        )
        team_member_ids = self.fields["team_member"].queryset.values_list("pk", flat=True)
        earliest_roll_map = _team_member_earliest_roll_start_map(team_member_ids)
        self.fields["team_member"].widget.attrs["data-roll-earliest-map"] = json.dumps(
            earliest_roll_map
        )
        if not self.is_bound and not (self.instance and self.instance.pk):
            if engagement is not None:
                earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
                if earliest_start is not None:
                    self.initial.setdefault("planned_start", earliest_start)
                if latest_finish is not None:
                    self.initial.setdefault("planned_finish", latest_finish)

    def clean(self):
        cleaned_data = super().clean()
        team_member = cleaned_data.get("team_member")
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        engagement = self.engagement or getattr(self.instance, "engagement", None)

        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )

        if engagement is not None and planned_start and planned_finish:
            earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
            if earliest_start is None or latest_finish is None:
                self.add_error(
                    "planned_start",
                    "Add engagement schedule rows before assigning team dates.",
                )
            else:
                if planned_start < earliest_start:
                    self.add_error(
                        "planned_start",
                        (
                            "Planned start cannot be earlier than engagement planned start "
                            f"({earliest_start.isoformat()})."
                        ),
                    )
                if planned_finish > latest_finish:
                    self.add_error(
                        "planned_finish",
                        (
                            "Planned finish cannot be later than engagement planned finish "
                            f"({latest_finish.isoformat()})."
                        ),
                    )

        if (
            engagement is not None
            and team_member is not None
            and planned_start
            and planned_finish
            and planned_finish >= planned_start
        ):
            if not _team_member_planned_dates_within_assignment_periods(
                team_member, planned_start, planned_finish
            ):
                field, message = _assignment_period_validation_error(team_member)
                self.add_error(field, message)
            overlap_qs = EngagementTeamAssignment.objects.filter(
                engagement=engagement,
                team_member=team_member,
            )
            if self.instance and self.instance.pk:
                overlap_qs = overlap_qs.exclude(pk=self.instance.pk)
            if _team_assignment_range_overlaps_qs(
                overlap_qs,
                planned_start=planned_start,
                planned_finish=planned_finish,
            ).exists():
                self.add_error(
                    "planned_start",
                    "This date range overlaps another assignment for this team member "
                    "on this engagement (ranges cannot share a day).",
                )

        return cleaned_data


class EngagementDivisionTeamAssignmentForm(forms.ModelForm):
    class Meta:
        model = EngagementDivisionTeamAssignment
        fields = ["team_member", "planned_start", "planned_finish"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, division=None, **kwargs):
        self.division = division
        super().__init__(*args, **kwargs)
        self.fields["team_member"].queryset = TeamMember.objects.order_by(
            "first_name", "last_name", "code"
        )
        team_member_ids = self.fields["team_member"].queryset.values_list("pk", flat=True)
        earliest_roll_map = _team_member_earliest_roll_start_map(team_member_ids)
        self.fields["team_member"].widget.attrs["data-roll-earliest-map"] = json.dumps(
            earliest_roll_map
        )
        if not self.is_bound and not (self.instance and self.instance.pk):
            if division is not None:
                if division.planned_start is not None:
                    self.initial.setdefault("planned_start", division.planned_start)
                if division.planned_finish is not None:
                    self.initial.setdefault("planned_finish", division.planned_finish)
                if (
                    self.initial.get("planned_start") is None
                    or self.initial.get("planned_finish") is None
                ):
                    earliest_start, latest_finish = _engagement_schedule_bounds(
                        division.engagement
                    )
                    if (
                        self.initial.get("planned_start") is None
                        and earliest_start is not None
                    ):
                        self.initial.setdefault("planned_start", earliest_start)
                    if (
                        self.initial.get("planned_finish") is None
                        and latest_finish is not None
                    ):
                        self.initial.setdefault("planned_finish", latest_finish)

    def clean(self):
        cleaned_data = super().clean()
        team_member = cleaned_data.get("team_member")
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        division = self.division or getattr(self.instance, "division", None)

        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )

        if division is not None and planned_start and planned_finish:
            if division.planned_start and planned_start < division.planned_start:
                self.add_error(
                    "planned_start",
                    (
                        "Planned start cannot be earlier than division planned start "
                        f"({division.planned_start.isoformat()})."
                    ),
                )
            if division.planned_finish and planned_finish > division.planned_finish:
                self.add_error(
                    "planned_finish",
                    (
                        "Planned finish cannot be later than division planned finish "
                        f"({division.planned_finish.isoformat()})."
                    ),
                )

            engagement = division.engagement
            earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
            if earliest_start is None or latest_finish is None:
                self.add_error(
                    "planned_start",
                    "Add engagement schedule rows before assigning team dates.",
                )
            else:
                if planned_start < earliest_start:
                    self.add_error(
                        "planned_start",
                        (
                            "Planned start cannot be earlier than engagement planned start "
                            f"({earliest_start.isoformat()})."
                        ),
                    )
                if planned_finish > latest_finish:
                    self.add_error(
                        "planned_finish",
                        (
                            "Planned finish cannot be later than engagement planned finish "
                            f"({latest_finish.isoformat()})."
                        ),
                    )

        if (
            division is not None
            and team_member is not None
            and planned_start
            and planned_finish
            and planned_finish >= planned_start
        ):
            if not _team_member_planned_dates_within_assignment_periods(
                team_member, planned_start, planned_finish
            ):
                field, message = _assignment_period_validation_error(team_member)
                self.add_error(field, message)
            overlap_qs = EngagementDivisionTeamAssignment.objects.filter(
                division=division,
                team_member=team_member,
            )
            if self.instance and self.instance.pk:
                overlap_qs = overlap_qs.exclude(pk=self.instance.pk)
            if _team_assignment_range_overlaps_qs(
                overlap_qs,
                planned_start=planned_start,
                planned_finish=planned_finish,
            ).exists():
                self.add_error(
                    "planned_start",
                    "This date range overlaps another assignment for this team member "
                    "on this division (ranges cannot share a day).",
                )

        return cleaned_data


class EngagementWorkAreaTeamAssignmentForm(forms.ModelForm):
    class Meta:
        model = EngagementWorkAreaTeamAssignment
        fields = ["team_member", "planned_start", "planned_finish", "assignment_notes"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "assignment_notes": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 4,
                    "placeholder": "Optional guidance for the assignee",
                }
            ),
        }

    def __init__(self, *args, work_area=None, **kwargs):
        self.work_area = work_area
        super().__init__(*args, **kwargs)
        engagement = getattr(work_area, "engagement", None)
        if engagement is None and getattr(self.instance, "pk", None):
            engagement = getattr(self.instance.work_area, "engagement", None)
        allowed_ids = _team_member_pks_assigned_to_engagement(engagement)
        self.fields["team_member"].queryset = _work_area_team_member_queryset_allowed_pks(
            allowed_ids, self.instance
        )
        self.fields["planned_start"].required = True
        self.fields["planned_finish"].required = True

    def clean_assignment_notes(self):
        return (self.cleaned_data.get("assignment_notes") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        work_area = self.work_area or getattr(self.instance, "work_area", None)
        team_member = cleaned_data.get("team_member")
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )
        if work_area is not None and team_member is not None:
            parent_ok = EngagementTeamAssignment.objects.filter(
                engagement=work_area.engagement,
                team_member=team_member,
            ).exists()
            if not parent_ok:
                self.add_error(
                    "team_member",
                    "Choose a team member who is assigned to this engagement.",
                )
        if work_area is None or team_member is None:
            return cleaned_data

        qs = EngagementWorkAreaTeamAssignment.objects.filter(
            work_area=work_area,
            team_member=team_member,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(
                "team_member",
                "This team member is already assigned to the selected work area.",
            )
        return cleaned_data


class DivisionWorkAreaTeamAssignmentForm(forms.ModelForm):
    class Meta:
        model = DivisionWorkAreaTeamAssignment
        fields = ["team_member", "planned_start", "planned_finish", "assignment_notes"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "assignment_notes": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 4,
                    "placeholder": "Optional guidance for the assignee",
                }
            ),
        }

    def __init__(self, *args, work_area=None, **kwargs):
        self.work_area = work_area
        super().__init__(*args, **kwargs)
        division = getattr(work_area, "division", None)
        if division is None and getattr(self.instance, "pk", None):
            division = getattr(self.instance.work_area, "division", None)
        allowed_ids = _team_member_pks_assigned_to_engagement_division(division)
        self.fields["team_member"].queryset = _work_area_team_member_queryset_allowed_pks(
            allowed_ids, self.instance
        )
        self.fields["planned_start"].required = True
        self.fields["planned_finish"].required = True

    def clean_assignment_notes(self):
        return (self.cleaned_data.get("assignment_notes") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        work_area = self.work_area or getattr(self.instance, "work_area", None)
        team_member = cleaned_data.get("team_member")
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )
        if work_area is not None and team_member is not None:
            parent_ok = EngagementDivisionTeamAssignment.objects.filter(
                division=work_area.division,
                team_member=team_member,
            ).exists()
            if not parent_ok:
                self.add_error(
                    "team_member",
                    "Choose a team member who is assigned to this engagement division.",
                )
        if work_area is None or team_member is None:
            return cleaned_data

        qs = DivisionWorkAreaTeamAssignment.objects.filter(
            work_area=work_area,
            team_member=team_member,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(
                "team_member",
                "This team member is already assigned to the selected work area.",
            )
        return cleaned_data


class EngagementWorkAreaForm(forms.ModelForm):
    class Meta:
        model = EngagementWorkArea
        fields = ["work_area_name", "documentation", "sort_order"]
        widgets = {
            "work_area_name": forms.TextInput(attrs={"class": "input-medium"}),
            "documentation": forms.Select(attrs={"class": "input-medium"}),
            "sort_order": forms.NumberInput(attrs={"class": "input-compact"}),
        }

    def __init__(self, *args, engagement=None, **kwargs):
        self.engagement = engagement
        super().__init__(*args, **kwargs)
        self.fields["documentation"].queryset = EngagementDocumentation.objects.order_by(
            "standard_document", "document_stage"
        )
        self.fields["documentation"].required = True
        self.fields["documentation"].empty_label = "— Select documentation —"
        self.fields["documentation"].label_from_instance = (
            lambda obj: f"{obj.standard_document} ({obj.get_document_stage_display()})"
        )
        if (
            engagement is not None
            and not self.is_bound
            and not getattr(self.instance, "pk", None)
            and self.fields["sort_order"].initial in (None, "", 0)
        ):
            max_order = (
                EngagementWorkArea.objects.filter(engagement=engagement).aggregate(
                    max_order=Max("sort_order")
                )["max_order"]
                or 0
            )
            self.fields["sort_order"].initial = max_order + 1

    def clean_work_area_name(self):
        name = (self.cleaned_data.get("work_area_name") or "").strip()
        if not name:
            raise forms.ValidationError("Work area name is required.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("work_area_name")
        engagement = self.engagement
        if engagement is None and self.instance.pk:
            engagement = self.instance.engagement
        if not name or engagement is None:
            return cleaned_data

        duplicates = EngagementWorkArea.objects.filter(
            engagement=engagement,
            work_area_name=name,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "work_area_name",
                "This work area name already exists for the engagement.",
            )
        return cleaned_data


class DivisionWorkAreaForm(forms.ModelForm):
    class Meta:
        model = DivisionWorkArea
        fields = ["work_area_name", "documentation", "sort_order"]
        widgets = {
            "work_area_name": forms.TextInput(attrs={"class": "input-medium"}),
            "documentation": forms.Select(attrs={"class": "input-medium"}),
            "sort_order": forms.NumberInput(attrs={"class": "input-compact"}),
        }

    def __init__(self, *args, division=None, **kwargs):
        self.division = division
        super().__init__(*args, **kwargs)
        self.fields["documentation"].queryset = EngagementDocumentation.objects.order_by(
            "standard_document", "document_stage"
        )
        self.fields["documentation"].required = True
        self.fields["documentation"].empty_label = "— Select documentation —"
        self.fields["documentation"].label_from_instance = (
            lambda obj: f"{obj.standard_document} ({obj.get_document_stage_display()})"
        )
        if (
            division is not None
            and not self.is_bound
            and not getattr(self.instance, "pk", None)
            and self.fields["sort_order"].initial in (None, "", 0)
        ):
            max_order = (
                DivisionWorkArea.objects.filter(division=division).aggregate(
                    max_order=Max("sort_order")
                )["max_order"]
                or 0
            )
            self.fields["sort_order"].initial = max_order + 1

    def clean_work_area_name(self):
        name = (self.cleaned_data.get("work_area_name") or "").strip()
        if not name:
            raise forms.ValidationError("Work area name is required.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("work_area_name")
        division = self.division
        if division is None and self.instance.pk:
            division = self.instance.division
        if not name or division is None:
            return cleaned_data

        duplicates = DivisionWorkArea.objects.filter(
            division=division,
            work_area_name=name,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "work_area_name",
                "This work area name already exists for the division.",
            )
        return cleaned_data


def _engagement_schedule_bounds(engagement):
    window = engagement.schedules.aggregate(
        earliest_start=Min("planned_start"),
        latest_finish=Max("planned_finish"),
    )
    return window["earliest_start"], window["latest_finish"]


def _team_assignment_range_overlaps_qs(qs, *, planned_start, planned_finish):
    """Inclusive dates: overlap if the ranges share at least one day."""
    return qs.filter(
        planned_start__lte=planned_finish,
        planned_finish__gte=planned_start,
    )


def _apply_work_area_schedule_window_errors(
    form,
    cleaned_data,
    *,
    engagement,
    division=None,
):
    planned_start = cleaned_data.get("planned_start")
    planned_finish = cleaned_data.get("planned_finish")
    actual_start = cleaned_data.get("actual_start")
    actual_finish = cleaned_data.get("actual_finish")

    if planned_start and planned_finish and planned_finish < planned_start:
        form.add_error(
            "planned_finish",
            "Planned finish cannot be before planned start.",
        )

    if actual_start and actual_finish and actual_finish < actual_start:
        form.add_error(
            "actual_finish",
            "Actual finish cannot be before actual start.",
        )

    if not planned_start or not planned_finish or engagement is None:
        return

    earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
    if earliest_start is None or latest_finish is None:
        # No engagement-level plan exists yet. Allow work-area save and let
        # the view layer optionally backfill engagement schedule from this row.
        return

    if planned_start < earliest_start:
        form.add_error(
            "planned_start",
            (
                "Planned start cannot be earlier than engagement planned start "
                f"({earliest_start.isoformat()})."
            ),
        )
    if planned_finish > latest_finish:
        form.add_error(
            "planned_finish",
            (
                "Planned finish cannot be later than engagement planned finish "
                f"({latest_finish.isoformat()})."
            ),
        )

    if division is not None:
        if (
            division.planned_start is not None
            and planned_start < division.planned_start
        ):
            form.add_error(
                "planned_start",
                (
                    "Planned start cannot be earlier than division planned start "
                    f"({division.planned_start.isoformat()})."
                ),
            )
        if (
            division.planned_finish is not None
            and planned_finish > division.planned_finish
        ):
            form.add_error(
                "planned_finish",
                (
                    "Planned finish cannot be later than division planned finish "
                    f"({division.planned_finish.isoformat()})."
                ),
            )


class EngagementWorkAreaPeriodForm(forms.ModelForm):
    class Meta:
        model = EngagementWorkAreaPeriod
        fields = [
            "planned_start",
            "planned_finish",
            "actual_start",
            "actual_finish",
        ]
        widgets = {
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, work_area=None, **kwargs):
        self.work_area = work_area
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        work_area = self.work_area
        if work_area is None and self.instance.pk:
            work_area = self.instance.work_area
        engagement = work_area.engagement if work_area else None
        if engagement is None:
            return cleaned_data
        _apply_work_area_schedule_window_errors(
            self,
            cleaned_data,
            engagement=engagement,
            division=None,
        )
        return cleaned_data


class DivisionWorkAreaPeriodForm(forms.ModelForm):
    class Meta:
        model = DivisionWorkAreaPeriod
        fields = [
            "planned_start",
            "planned_finish",
            "actual_start",
            "actual_finish",
        ]
        widgets = {
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, work_area=None, **kwargs):
        self.work_area = work_area
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        work_area = self.work_area
        if work_area is None and self.instance.pk:
            work_area = self.instance.work_area
        division = work_area.division if work_area else None
        engagement = division.engagement if division else None
        if engagement is None:
            return cleaned_data
        _apply_work_area_schedule_window_errors(
            self,
            cleaned_data,
            engagement=engagement,
            division=division,
        )
        return cleaned_data


class EngagementDivisionForm(forms.ModelForm):
    engagement = EngagementModelChoiceField(
        queryset=Engagement.objects.none(),
        widget=forms.Select(attrs={"class": "input-long"}),
    )

    class Meta:
        model = EngagementDivision
        fields = [
            "engagement",
            "division_name",
            "division_mail_ids",
            "planned_start",
            "planned_finish",
            "actual_start",
            "actual_finish",
        ]
        widgets = {
            "division_name": forms.TextInput(attrs={"class": "input-medium"}),
            "division_mail_ids": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 3,
                    "placeholder": "Comma/newline separated email IDs",
                }
            ),
            "planned_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "planned_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_start": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "actual_finish": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["engagement"].queryset = (
            Engagement.objects.all()
            .select_related("client", "fiscal_year", "service")
            .order_by(
                "client__client_name",
                "fiscal_year__fy_no",
                "service__service_desc",
            )
        )
        if (
            not self.is_bound
            and self.instance
            and getattr(self.instance, "pk", None)
            and not (self.instance.division_mail_ids or "").strip()
        ):
            engagement = getattr(self.instance, "engagement", None)
            defaults = []
            if engagement is not None:
                if (engagement.engagement_mail_id or "").strip():
                    defaults.append((engagement.engagement_mail_id or "").strip())
                defaults.extend(
                    [
                        p.strip()
                        for p in re.split(
                            r"[,\n;]+", (engagement.additional_mail_ids or "")
                        )
                        if p.strip()
                    ]
                )
                if getattr(engagement, "client", None) and (
                    engagement.client.mail_id or ""
                ).strip():
                    defaults.append((engagement.client.mail_id or "").strip())
                if getattr(engagement, "client", None):
                    defaults.extend(
                        [
                            p.strip()
                            for p in re.split(
                                r"[,\n;]+",
                                (engagement.client.additional_mail_ids or ""),
                            )
                            if p.strip()
                        ]
                    )
            defaults = list(dict.fromkeys(defaults))
            if defaults:
                self.initial.setdefault("division_mail_ids", ", ".join(defaults))

    def clean_division_name(self):
        division_name = (self.cleaned_data.get("division_name") or "").strip()
        if not division_name:
            raise forms.ValidationError("Engagement division is required.")
        return division_name

    def clean_division_mail_ids(self):
        raw = self.cleaned_data.get("division_mail_ids") or ""
        parts = [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]

        engagement = self.cleaned_data.get("engagement") or getattr(
            self.instance, "engagement", None
        )
        if not parts and engagement is not None:
            defaults = []
            if (engagement.engagement_mail_id or "").strip():
                defaults.append((engagement.engagement_mail_id or "").strip())
            defaults.extend(
                [
                    p.strip()
                    for p in re.split(r"[,\n;]+", (engagement.additional_mail_ids or ""))
                    if p.strip()
                ]
            )
            if getattr(engagement, "client", None) and (
                engagement.client.mail_id or ""
            ).strip():
                defaults.append((engagement.client.mail_id or "").strip())
            if getattr(engagement, "client", None):
                defaults.extend(
                    [
                        p.strip()
                        for p in re.split(
                            r"[,\n;]+", (engagement.client.additional_mail_ids or "")
                        )
                        if p.strip()
                    ]
                )
            parts = list(dict.fromkeys(defaults))

        invalid = []
        for item in parts:
            try:
                validate_email(item)
            except ValidationError:
                invalid.append(item)
        if invalid:
            raise forms.ValidationError("Invalid email(s): " + ", ".join(invalid[:5]))
        return ", ".join(parts)

    def clean(self):
        cleaned_data = super().clean()
        engagement = cleaned_data.get("engagement")
        planned_start = cleaned_data.get("planned_start")
        planned_finish = cleaned_data.get("planned_finish")
        actual_start = cleaned_data.get("actual_start")
        actual_finish = cleaned_data.get("actual_finish")

        if planned_start and planned_finish and planned_finish < planned_start:
            self.add_error(
                "planned_finish",
                "Planned finish cannot be before planned start.",
            )
        if actual_start and actual_finish and actual_finish < actual_start:
            self.add_error(
                "actual_finish",
                "Actual finish cannot be before actual start.",
            )

        if engagement is None:
            return cleaned_data

        has_any_date = planned_start is not None or planned_finish is not None
        if not has_any_date:
            return cleaned_data

        window = engagement.schedules.aggregate(
            earliest_start=Min("planned_start"),
            latest_finish=Max("planned_finish"),
        )
        earliest_start = window["earliest_start"]
        latest_finish = window["latest_finish"]

        if earliest_start is None or latest_finish is None:
            self.add_error(
                "engagement",
                "Add engagement schedule rows before mapping division dates.",
            )
            return cleaned_data

        if planned_start is not None:
            if planned_start < earliest_start:
                self.add_error(
                    "planned_start",
                    f"Planned start cannot be earlier than engagement planned start ({earliest_start.isoformat()}).",
                )
            if planned_start > latest_finish:
                self.add_error(
                    "planned_start",
                    f"Planned start cannot be later than engagement planned finish ({latest_finish.isoformat()}).",
                )

        if planned_finish is not None:
            if planned_finish > latest_finish:
                self.add_error(
                    "planned_finish",
                    f"Planned finish cannot be later than engagement planned finish ({latest_finish.isoformat()}).",
                )
            if planned_finish < earliest_start:
                self.add_error(
                    "planned_finish",
                    f"Planned finish cannot be earlier than engagement planned start ({earliest_start.isoformat()}).",
                )

        return cleaned_data


class EngagementDocumentationMapForm(forms.ModelForm):
    class Meta:
        model = EngagementDocumentationMap
        fields = ["documentation", "documentation_date"]
        widgets = {
            "documentation": forms.Select(attrs={"class": "input-long"}),
            "documentation_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.engagement = kwargs.pop("engagement", None)
        super().__init__(*args, **kwargs)
        base_queryset = (
            self.fields["documentation"]
            .queryset.prefetch_related("applicable_classifications")
            .order_by("document_stage", "standard_document")
        )
        engagement = self.engagement or getattr(self.instance, "engagement", None)
        if engagement is not None:
            used_doc_ids_qs = EngagementDocumentationMap.objects.filter(
                engagement=engagement
            )
            if self.instance and self.instance.pk and self.instance.documentation_id:
                used_doc_ids_qs = used_doc_ids_qs.exclude(
                    documentation_id=self.instance.documentation_id
                )
            base_queryset = base_queryset.exclude(
                pk__in=used_doc_ids_qs.values_list("documentation_id", flat=True)
            )
            include_pk = None
            if self.instance and self.instance.pk and self.instance.documentation_id:
                include_pk = self.instance.documentation_id
            base_queryset = filter_engagement_documentation_by_client_classification(
                base_queryset,
                engagement.client,
                include_documentation_pk=include_pk,
            )

        if not (self.instance and self.instance.pk):
            self.fields["documentation_date"].initial = timezone.localdate()

        initial_id = ""
        initial_label = ""
        if self.instance and self.instance.pk and self.instance.documentation_id:
            initial_id = str(self.instance.documentation_id)
            initial_label = _documentation_choice_label(self.instance.documentation)
            self.fields["documentation"].queryset = base_queryset
            self.fields["documentation"].label_from_instance = _documentation_choice_label
        else:
            self.fields["documentation"] = forms.ModelMultipleChoiceField(
                queryset=base_queryset,
                required=True,
                label="Documentation",
            )
            self.fields["documentation"].label_from_instance = _documentation_choice_label

        tid = (self.auto_id % "documentation") if self.auto_id else "documentation"
        search_url = (
            reverse(
                "engagement_documentation_option_search",
                kwargs={"engagement_pk": engagement.pk},
            )
            if engagement is not None
            else ""
        )
        self.fields["documentation"].widget = TeamMemberPickerWidget(
            attrs={
                "id": tid,
                "data_search_url": search_url,
                "data_for_user": initial_id,
                "data_multiple": "0" if initial_id else "1",
                "data_initial_ids": "",
                "data_search_placeholder": "Search documentation...",
                "data_search_aria": "Search documentation",
                "data_search_help": (
                    "Type to search documentation. Results are limited to items whose "
                    "Applicable To includes this client's classification; already mapped "
                    "items are excluded (except the current item when editing)."
                ),
                "data_clear_label": "Clear documentation link",
                "data_empty_text": "No documentation matches.",
                "data_error_text": "Could not load documentation results.",
                "data_initial_id": initial_id,
                "data_initial_label": initial_label,
            }
        )

    def clean_documentation(self):
        documentation = self.cleaned_data.get("documentation")
        engagement = self.engagement or getattr(self.instance, "engagement", None)
        if documentation is None or engagement is None:
            return documentation

        docs = (
            list(documentation)
            if hasattr(documentation, "__iter__")
            and not isinstance(documentation, EngagementDocumentation)
            else [documentation]
        )
        cl = engagement.client.classification
        for doc in docs:
            if not doc.applicable_classifications.filter(pk=cl.pk).exists():
                raise forms.ValidationError(
                    "Each selected item must list this client's classification under "
                    f"Applicable To ({cl.classification_name})."
                )
        duplicate_exists = EngagementDocumentationMap.objects.filter(
            engagement=engagement,
            documentation__in=docs,
        )
        if self.instance and self.instance.pk:
            duplicate_exists = duplicate_exists.exclude(pk=self.instance.pk)
        if duplicate_exists.exists():
            raise forms.ValidationError(
                "One or more selected documentation items are already mapped to the engagement."
            )
        return documentation

    def _post_clean(self):
        # Create mode uses ModelMultipleChoiceField for "documentation". Skip model binding
        # in ModelForm._post_clean because model FK expects a single instance.
        if (
            self.instance is not None
            and self.instance.pk is None
            and isinstance(
                self.fields.get("documentation"),
                forms.ModelMultipleChoiceField,
            )
        ):
            return
        super()._post_clean()


class EngagementDivisionDocumentationMapForm(forms.ModelForm):
    class Meta:
        model = EngagementDivisionDocumentationMap
        fields = ["documentation"]
        widgets = {
            "documentation": forms.Select(attrs={"class": "input-long"}),
        }

    def __init__(self, *args, **kwargs):
        self.division = kwargs.pop("division", None)
        super().__init__(*args, **kwargs)
        base_queryset = (
            self.fields["documentation"]
            .queryset.prefetch_related("applicable_classifications")
            .order_by("document_stage", "standard_document")
        )
        division = self.division or getattr(self.instance, "division", None)
        if division is not None:
            used_doc_ids_qs = EngagementDivisionDocumentationMap.objects.filter(
                division=division
            )
            if self.instance and self.instance.pk and self.instance.documentation_id:
                used_doc_ids_qs = used_doc_ids_qs.exclude(
                    documentation_id=self.instance.documentation_id
                )
            base_queryset = base_queryset.exclude(
                pk__in=used_doc_ids_qs.values_list("documentation_id", flat=True)
            )
            include_pk = None
            if self.instance and self.instance.pk and self.instance.documentation_id:
                include_pk = self.instance.documentation_id
            base_queryset = filter_engagement_documentation_by_client_classification(
                base_queryset,
                division.engagement.client,
                include_documentation_pk=include_pk,
            )

        initial_id = ""
        initial_label = ""
        if self.instance and self.instance.pk and self.instance.documentation_id:
            initial_id = str(self.instance.documentation_id)
            initial_label = _documentation_choice_label(self.instance.documentation)
            self.fields["documentation"].queryset = base_queryset
            self.fields["documentation"].label_from_instance = _documentation_choice_label
        else:
            self.fields["documentation"] = forms.ModelMultipleChoiceField(
                queryset=base_queryset,
                required=True,
                label="Documentation",
            )
            self.fields["documentation"].label_from_instance = _documentation_choice_label

        tid = (self.auto_id % "documentation") if self.auto_id else "documentation"
        search_url = (
            reverse(
                "engagement_division_documentation_option_search",
                kwargs={"division_pk": division.pk},
            )
            if division is not None
            else ""
        )
        self.fields["documentation"].widget = TeamMemberPickerWidget(
            attrs={
                "id": tid,
                "data_search_url": search_url,
                "data_for_user": initial_id,
                "data_multiple": "0" if initial_id else "1",
                "data_initial_ids": "",
                "data_search_placeholder": "Search documentation...",
                "data_search_aria": "Search documentation",
                "data_search_help": (
                    "Type to search documentation. Results are limited to items whose "
                    "Applicable To includes this engagement client's classification; "
                    "already mapped items are excluded (except the current item when editing)."
                ),
                "data_clear_label": "Clear documentation link",
                "data_empty_text": "No documentation matches.",
                "data_error_text": "Could not load documentation results.",
                "data_initial_id": initial_id,
                "data_initial_label": initial_label,
            }
        )

    def clean_documentation(self):
        documentation = self.cleaned_data.get("documentation")
        division = self.division or getattr(self.instance, "division", None)
        if documentation is None or division is None:
            return documentation

        docs = (
            list(documentation)
            if hasattr(documentation, "__iter__")
            and not isinstance(documentation, EngagementDocumentation)
            else [documentation]
        )
        cl = division.engagement.client.classification
        for doc in docs:
            if not doc.applicable_classifications.filter(pk=cl.pk).exists():
                raise forms.ValidationError(
                    "Each selected item must list this engagement client's classification "
                    f"under Applicable To ({cl.classification_name})."
                )
        duplicate_exists = EngagementDivisionDocumentationMap.objects.filter(
            division=division,
            documentation__in=docs,
        )
        if self.instance and self.instance.pk:
            duplicate_exists = duplicate_exists.exclude(pk=self.instance.pk)
        if duplicate_exists.exists():
            raise forms.ValidationError(
                "One or more selected documentation items are already mapped to the division."
            )
        return documentation

    def _post_clean(self):
        # Create mode uses ModelMultipleChoiceField for "documentation". Skip model binding
        # in ModelForm._post_clean because model FK expects a single instance.
        if (
            self.instance is not None
            and self.instance.pk is None
            and isinstance(
                self.fields.get("documentation"),
                forms.ModelMultipleChoiceField,
            )
        ):
            return
        super()._post_clean()
