from django import forms

from sales.clients.models import Client
from sales.services.models import Service

from sales.udins.models import Udin
from sales.udins.service_fy_build import derive_service_fy, normalize_service_fy
from sales.udins.service_rules import is_certification_service
from sales.udins.udin_no import normalize_udin

from .constants import STATUS_CHOICES


class UdinForm(forms.ModelForm):
    class Meta:
        model = Udin
        fields = [
            "udin",
            "remarks",
            "date_of_signing_of_document",
            "create_date",
            "client",
            "service",
            "ay_fy",
            "service_remarks",
            "status",
            "inv_no",
            "inv_date",
            "inv_tv_amount",
        ]
        labels = {
            "ay_fy": "Service FY",
        }
        widgets = {
            "udin": forms.TextInput(attrs={"class": "input-medium"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
            "service_remarks": forms.Textarea(attrs={"rows": 2}),
            "date_of_signing_of_document": forms.TextInput(attrs={"class": "input-compact"}),
            "create_date": forms.DateInput(attrs={"type": "date", "class": "input-compact"}),
            "ay_fy": forms.TextInput(
                attrs={
                    "class": "input-compact",
                    "placeholder": "FY26",
                    "autocomplete": "off",
                    "maxlength": "4",
                }
            ),
            "client": forms.Select(attrs={"class": "input-medium"}),
            "service": forms.Select(attrs={"class": "input-medium"}),
            "status": forms.Select(attrs={"class": "input-medium"}, choices=STATUS_CHOICES),
            "inv_no": forms.TextInput(attrs={"class": "input-compact"}),
            "inv_date": forms.DateInput(attrs={"type": "date", "class": "input-compact"}),
            "inv_tv_amount": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("client_name", "client_code")
        self.fields["service"].queryset = Service.objects.order_by("service_desc", "service_code")

    def clean_udin(self):
        value = normalize_udin(self.cleaned_data.get("udin"))
        if not value:
            raise forms.ValidationError("UDIN is required.")
        qs = Udin.objects.filter(udin=value)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This UDIN already exists.")
        return value

    def clean_ay_fy(self):
        raw = (self.cleaned_data.get("ay_fy") or "").strip()
        if not raw:
            return ""
        normalized = normalize_service_fy(raw)
        if not normalized:
            raise forms.ValidationError("Service FY must be FY26, FY27, etc.")
        return normalized

    def clean(self):
        cleaned = super().clean()
        service = cleaned.get("service")
        if is_certification_service(service):
            derived = derive_service_fy(
                service=service,
                date_of_signing_of_document=cleaned.get("date_of_signing_of_document") or "",
            )
            if derived:
                cleaned["ay_fy"] = derived

        return cleaned

