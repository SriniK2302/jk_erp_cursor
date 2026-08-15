import json

from django import forms

from hr.teams.models import TeamMember

from engagements.models import EngagementTeamAssignment

from .assignment_helpers import (
    _assignment_period_validation_error,
    _team_member_earliest_roll_start_map,
    _team_member_planned_dates_within_assignment_periods,
)
from .schedule_helpers import (
    _engagement_schedule_bounds,
    _team_assignment_range_overlaps_qs,
)

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
