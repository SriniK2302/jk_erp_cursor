from django import forms

from .models import Qualification

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


class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = ["qualification_desc", "qualification_code"]
        widgets = {
            "qualification_desc": forms.TextInput(attrs={"class": "input-long"}),
            "qualification_code": forms.TextInput(attrs={"class": "input-compact"}),
        }

    def clean_qualification_code(self):
        code = (self.cleaned_data.get("qualification_code") or "").strip().upper()[:4]
        if code in COMMON_WORD_CODES and code:
            code = f"{code[:-1]}X"
        return code
