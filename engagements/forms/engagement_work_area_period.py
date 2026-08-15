from django import forms

from engagements.models import EngagementWorkAreaPeriod

from .schedule_helpers import _apply_work_area_schedule_window_errors

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
