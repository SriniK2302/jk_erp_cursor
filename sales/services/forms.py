from django import forms

from .models import Service

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


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["service_desc", "service_code"]
        widgets = {
            "service_desc": forms.TextInput(attrs={"class": "input-long"}),
            "service_code": forms.TextInput(attrs={"class": "input-compact"}),
        }

    def clean_service_code(self):
        code = (self.cleaned_data.get("service_code") or "").strip().upper()[:4]
        if code in COMMON_WORD_CODES and code:
            code = f"{code[:-1]}X"
        return code
