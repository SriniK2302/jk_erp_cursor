from datetime import date

from django import forms

from .models import FiscalYear


def derive_fy_dates(fy_no: str):
    fy_code = (fy_no or "").strip().upper()[:4]
    if len(fy_code) != 4 or not fy_code.startswith("FY") or not fy_code[2:].isdigit():
        return None

    end_year = 2000 + int(fy_code[2:])
    return (
        date(end_year - 1, 4, 1),
        date(end_year, 3, 31),
    )


class FiscalYearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ["fy_no", "start_date", "end_date"]
        widgets = {
            "fy_no": forms.TextInput(attrs={"class": "input-compact"}),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact", "readonly": "readonly"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact", "readonly": "readonly"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].required = False
        self.fields["end_date"].required = False

    def clean_fy_no(self):
        fy_no = (self.cleaned_data.get("fy_no") or "").strip().upper()[:4]
        if derive_fy_dates(fy_no) is None:
            raise forms.ValidationError("FY No must be in format FY25, FY26, etc.")
        return fy_no

    def clean(self):
        cleaned_data = super().clean()
        fy_no = cleaned_data.get("fy_no")
        fy_dates = derive_fy_dates(fy_no) if fy_no else None
        if fy_dates is not None:
            cleaned_data["start_date"], cleaned_data["end_date"] = fy_dates
        return cleaned_data
