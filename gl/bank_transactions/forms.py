from django import forms

from .models import BankTransactionSourceOb


class BankTransactionSourceObForm(forms.ModelForm):
    class Meta:
        model = BankTransactionSourceOb
        fields = ["source_ac", "ym", "ob"]
        widgets = {
            "source_ac": forms.Select(attrs={"class": "input-compact"}),
            "ym": forms.TextInput(attrs={"class": "input-compact", "maxlength": 5, "placeholder": "MYYMM"}),
            "ob": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
        }

    def clean_ym(self):
        ym = (self.cleaned_data.get("ym") or "").strip().upper()
        if len(ym) != 5 or ym[0] != "M" or not ym[1:].isdigit():
            raise forms.ValidationError("YM must be in format MYYMM, e.g. M2601.")
        return ym
    