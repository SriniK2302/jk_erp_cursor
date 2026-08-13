from django import forms

from .models import Grade

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


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["grade_desc", "grade_code"]
        widgets = {
            "grade_desc": forms.TextInput(attrs={"class": "input-medium"}),
            "grade_code": forms.TextInput(attrs={"class": "input-compact"}),
        }

    def clean_grade_code(self):
        code = (self.cleaned_data.get("grade_code") or "").strip().upper()[:4]
        if code in COMMON_WORD_CODES and code:
            code = f"{code[:-1]}X"
        return code
