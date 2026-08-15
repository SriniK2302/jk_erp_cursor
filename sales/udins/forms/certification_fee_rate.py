from django import forms

from sales.clients.models import Client

from sales.udins.models import CertificationFeeRate

from .certification_helpers import certification_service_queryset


class CertificationFeeRateForm(forms.ModelForm):
    class Meta:
        model = CertificationFeeRate
        fields = ["client", "service", "fee_amount"]
        widgets = {
            "client": forms.Select(attrs={"class": "input-medium"}),
            "service": forms.Select(attrs={"class": "input-medium"}),
            "fee_amount": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("client_name", "client_code")
        self.fields["service"].queryset = certification_service_queryset()

    def clean_service(self):
        service = self.cleaned_data["service"]
        if "certification" not in (service.service_desc or "").lower():
            raise forms.ValidationError("Only certification services are allowed.")
        return service

    def clean(self):
        cleaned = super().clean()
        client = cleaned.get("client")
        service = cleaned.get("service")
        if client and service:
            qs = CertificationFeeRate.objects.filter(client=client, service=service)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A fee rate already exists for this client and service.")
        return cleaned
