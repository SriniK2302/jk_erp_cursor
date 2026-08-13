from django import forms

from .models import (
    TeamMember,
    TeamMemberQualificationPeriod,
    TeamMemberRollPeriod,
)

COMMON_WORD_CODES = {
    "THIS",
    "THAT",
    "THEN",
    "THEM",
    "THEY",
    "WITH",
    "WERE",
    "FROM",
    "YOUR",
    "HAVE",
    "WILL",
    "INTO",
    "ONTO",
    "HERE",
    "THUS",
    "WHEN",
    "WHAT",
}


class TeamMemberForm(forms.ModelForm):
    class Meta:
        model = TeamMember
        fields = ["first_name", "last_name", "called_as", "code", "work_email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input-medium"}),
            "last_name": forms.TextInput(attrs={"class": "input-medium"}),
            "called_as": forms.TextInput(attrs={"class": "input-medium"}),
            "code": forms.TextInput(attrs={"class": "input-compact"}),
            "work_email": forms.EmailInput(attrs={"class": "input-medium"}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()[:4]
        if code in COMMON_WORD_CODES and code:
            code = f"{code[:-1]}X"
        return code

    def clean_work_email(self):
        raw = (self.cleaned_data.get("work_email") or "").strip()
        return raw or ""


class TeamMemberRollPeriodForm(forms.ModelForm):
    class Meta:
        model = TeamMemberRollPeriod
        fields = ["from_date", "to_date", "notes"]
        widgets = {
            "from_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "to_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
            "notes": forms.TextInput(attrs={"class": "input-long"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        if from_date and to_date and to_date < from_date:
            self.add_error("to_date", "To date cannot be before from date.")
        return cleaned_data


class TeamMemberQualificationPeriodForm(forms.ModelForm):
    class Meta:
        model = TeamMemberQualificationPeriod
        fields = ["qualification", "from_date", "to_date"]
        widgets = {
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


