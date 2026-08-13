from django import forms
import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import Client, ClientTaxProfile

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


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "client_name",
            "client_short_name",
            "client_code",
            "classification",
            "address_1",
            "address_2",
            "area",
            "city_state_pincode",
            "state",
            "pincode",
            "contact_person",
            "mail_id",
            "additional_mail_ids",
            "billing_gstn",
            "invoice_tax_type",
            "is_active",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={"class": "input-long"}),
            "client_short_name": forms.TextInput(attrs={"class": "input-medium"}),
            "client_code": forms.TextInput(attrs={"class": "input-compact"}),
            "classification": forms.Select(attrs={"class": "input-medium"}),
            "address_1": forms.TextInput(attrs={"class": "input-long"}),
            "address_2": forms.TextInput(attrs={"class": "input-long"}),
            "area": forms.TextInput(attrs={"class": "input-medium"}),
            "city_state_pincode": forms.TextInput(attrs={"class": "input-long"}),
            "state": forms.TextInput(attrs={"class": "input-medium"}),
            "pincode": forms.TextInput(attrs={"class": "input-compact"}),
            "contact_person": forms.TextInput(attrs={"class": "input-medium"}),
            "mail_id": forms.EmailInput(attrs={"class": "input-medium"}),
            "additional_mail_ids": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 3,
                    "placeholder": "Comma/newline separated additional email IDs",
                }
            ),
            "billing_gstn": forms.TextInput(attrs={"class": "input-medium"}),
            "invoice_tax_type": forms.Select(attrs={"class": "input-medium"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classification"].queryset = (
            self.fields["classification"].queryset.order_by("classification_name")
        )
        self.fields["invoice_tax_type"].required = False

    def clean_invoice_tax_type(self):
        v = self.cleaned_data.get("invoice_tax_type")
        if not v:
            return Client.INVOICE_TAX_GST
        return v

    def clean_client_code(self):
        code = (self.cleaned_data.get("client_code") or "").strip().upper()[:4]
        if code in COMMON_WORD_CODES and code:
            code = f"{code[:-1]}X"
        return code

    def clean_classification(self):
        classification = self.cleaned_data.get("classification")
        if not classification:
            raise forms.ValidationError("Classification is required.")
        return classification

    def clean_address_1(self):
        return (self.cleaned_data.get("address_1") or "").strip()

    def clean_address_2(self):
        return (self.cleaned_data.get("address_2") or "").strip()

    def clean_area(self):
        return (self.cleaned_data.get("area") or "").strip()

    def clean_city_state_pincode(self):
        return (self.cleaned_data.get("city_state_pincode") or "").strip()

    def clean_state(self):
        return (self.cleaned_data.get("state") or "").strip()

    def clean_pincode(self):
        return (self.cleaned_data.get("pincode") or "").strip()

    def clean_contact_person(self):
        return (self.cleaned_data.get("contact_person") or "").strip()

    def clean_mail_id(self):
        return (self.cleaned_data.get("mail_id") or "").strip()

    def clean_additional_mail_ids(self):
        raw = self.cleaned_data.get("additional_mail_ids") or ""
        entries = [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]
        invalid = []
        for item in entries:
            try:
                validate_email(item)
            except ValidationError:
                invalid.append(item)
        if invalid:
            raise forms.ValidationError("Invalid email(s): " + ", ".join(invalid[:5]))
        return ", ".join(entries)

    def clean_billing_gstn(self):
        return (self.cleaned_data.get("billing_gstn") or "").strip().upper()


class ClientTaxProfileForm(forms.ModelForm):
    class Meta:
        model = ClientTaxProfile
        fields = ["pan", "tax_password", "date_of_formation"]
        widgets = {
            "pan": forms.TextInput(
                attrs={"class": "input-compact", "maxlength": "10", "placeholder": "ABCDE1234F"}
            ),
            "tax_password": forms.TextInput(attrs={"class": "input-compact"}),
            "date_of_formation": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def clean_pan(self):
        pan = (self.cleaned_data.get("pan") or "").strip().upper()
        if not pan:
            return ""
        if len(pan) != 10:
            raise forms.ValidationError("PAN must be exactly 10 characters.")
        import re

        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            raise forms.ValidationError("PAN format must be like ABCDE1234F.")
        return pan
