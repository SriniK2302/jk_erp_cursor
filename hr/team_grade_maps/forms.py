from django import forms

from hr.teams.rules import (
    get_team_grade_mapping_defaults,
    is_grade_period_to_date_locked,
    locked_grade_period_to_date,
)

from .models import TeamMemberGradePeriod


class TeamGradeMapForm(forms.ModelForm):
    class Meta:
        model = TeamMemberGradePeriod
        fields = ["team_member", "grade", "from_date", "to_date"]
        widgets = {
            "team_member": forms.Select(attrs={"class": "input-medium"}),
            "grade": forms.Select(attrs={"class": "input-medium"}),
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
            self.fields["team_member"].queryset.order_by(
                "first_name", "last_name", "code"
            )
        )
        self.fields["grade"].queryset = self.fields["grade"].queryset.order_by(
            "grade_desc", "grade_code"
        )

        if self.instance and self.instance.pk and is_grade_period_to_date_locked(
            self.instance
        ):
            locked_to_date = locked_grade_period_to_date(self.instance)
            self.fields["to_date"].initial = locked_to_date
            self.fields["to_date"].widget.attrs["readonly"] = "readonly"
        else:
            self.fields["to_date"].widget.attrs.pop("readonly", None)
            self.fields["to_date"].widget.attrs.pop("disabled", None)

    def clean(self):
        cleaned_data = super().clean()
        team_member = cleaned_data.get("team_member")
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")

        if team_member is None:
            return cleaned_data

        defaults = get_team_grade_mapping_defaults(
            team_member,
            period=self.instance if self.instance and self.instance.pk else None,
            exclude_period_id=self.instance.pk if self.instance and self.instance.pk else None,
        )
        if not defaults["has_roll_period"]:
            self.add_error(
                "team_member",
                "Add at least one on-roll period before mapping a grade.",
            )
            return cleaned_data

        start_date = defaults["from_date"]

        if not (self.instance and self.instance.pk):
            cleaned_data["from_date"] = start_date
            from_date = start_date

        if self.instance and self.instance.pk and is_grade_period_to_date_locked(
            self.instance
        ):
            cleaned_data["to_date"] = locked_grade_period_to_date(self.instance)
            to_date = cleaned_data["to_date"]

        if from_date and to_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be before from date.")
        return cleaned_data
