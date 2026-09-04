from django import forms

from .models import BankTransactionSourceOb, Fb, SourceBankCashAc


class BankTransactionSourceObForm(forms.ModelForm):
    class Meta:
        model = BankTransactionSourceOb
        fields = ["source_ac", "ym", "ob_debit", "ob_credit"]
        widgets = {
            "source_ac": forms.Select(attrs={"class": "input-compact"}),
            "ym": forms.TextInput(attrs={"class": "input-compact", "maxlength": 5, "placeholder": "MYYMM"}),
            "ob_debit": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
            "ob_credit": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
        }

    def clean_ym(self):
        ym = (self.cleaned_data.get("ym") or "").strip().upper()
        if len(ym) != 5 or ym[0] != "M" or not ym[1:].isdigit():
            raise forms.ValidationError("YM must be in format MYYMM, e.g. M2601.")
        return ym

class SourceBankCashAcForm(forms.ModelForm):
    class Meta:
        model = SourceBankCashAc
        fields = ["source_ac", "bank_name", "account_type", "fb_code"]
        widgets = {
            "source_ac": forms.TextInput(attrs={"class": "input-compact", "maxlength": 15}),
            "bank_name": forms.TextInput(attrs={"class": "input-compact", "maxlength": 50}),
            "account_type": forms.Select(attrs={"class": "input-compact"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        codes = list(Fb.objects.order_by("fb_code").values_list("fb_code", "fb_desc"))
        choices = [("", "— Select FB —")] + [
            (code, f"{code} — {desc}" if desc else code) for code, desc in codes
        ]
        self.fields["fb_code"] = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(attrs={"class": "input-compact"}),
            required=True,
        )


class FbForm(forms.ModelForm):
    class Meta:
        model = Fb
        fields = ["fb_code", "fb_desc", "entity"]
        widgets = {
            "fb_code": forms.TextInput(attrs={"class": "input-compact", "maxlength": 20}),
            "fb_desc": forms.TextInput(attrs={"class": "input-compact", "maxlength": 255}),
            "entity": forms.TextInput(attrs={"class": "input-compact", "maxlength": 100}),
        }
        