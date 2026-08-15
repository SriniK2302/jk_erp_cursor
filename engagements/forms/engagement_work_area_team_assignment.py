from django import forms

from engagements.models import (
    EngagementTeamAssignment,
    EngagementWorkAreaTeamAssignment,
)

from .assignment_helpers import (
    _team_member_pks_assigned_to_engagement,
    _work_area_team_member_queryset_allowed_pks,
)

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
