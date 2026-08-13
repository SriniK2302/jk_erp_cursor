from django import forms

from .models import TeamMemberQualificationPeriod


class TeamQualificationMapForm(forms.ModelForm):
    class Meta:
        model = TeamMemberQualificationPeriod
        fields = ["team_member", "qualification", "from_date", "to_date"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "qualification": forms.Select(attrs={"class": "input-medium"}),
            "from_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "to_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["team_member"].queryset = (
            self.fields["team_member"]
            .queryset.order_by("first_name", "last_name", "code")
        )
        self.fields["qualification"].queryset = (
            self.fields["qualification"]
            .queryset.order_by("qualification_desc", "qualification_code")
        )

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be before from date.")
        return cleaned_data
