from django import forms

from engagements.models import EngagementSchedule

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
