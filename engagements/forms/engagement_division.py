import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Max, Min

from engagements.models import Engagement, EngagementDivision

from .engagement_fields import EngagementModelChoiceField

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
