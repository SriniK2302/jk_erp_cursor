from django import forms
from sales.clients.models import Client
from sales.services.models import Service

from .models import CertificationFeeRate, CertificationPeriodFee, Udin
from .service_fy_build import derive_service_fy, normalize_service_fy
from .service_rules import is_certification_service
from .udin_no import normalize_udin


def certification_service_queryset():
    return Service.objects.filter(service_desc__icontains="certification").order_by(
        "service_desc", "service_code"
    )

STATUS_CHOICES = (
    ("", "---------"),
    ("Active", "Active"),
    ("Revoked", "Revoked"),
)


class UdinClientBulkUpdateForm(forms.Form):
    prefix = forms.CharField(
        label="Chars in Remarks",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "input-medium",
                "placeholder": "Type chars to match",
            }
        ),
    )
    client = forms.ModelChoiceField(
        label="Client",
        queryset=Client.objects.none(),
        widget=forms.Select(attrs={"class": "input-medium"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("client_name", "client_code")

    def clean_prefix(self):
        value = (self.cleaned_data.get("prefix") or "").strip()
        if not value:
            raise forms.ValidationError("Enter left-side characters to match remarks.")
        return value


class UdinServiceBulkUpdateForm(forms.Form):
    prefix = forms.CharField(
        label="Chars in Remarks",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "input-medium",
                "placeholder": "Type chars to match",
            }
        ),
    )
    service = forms.ModelChoiceField(
        label="Service",
        queryset=Service.objects.none(),
        widget=forms.Select(attrs={"class": "input-medium"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.order_by("service_desc", "service_code")

    def clean_prefix(self):
        value = (self.cleaned_data.get("prefix") or "").strip()
        if not value:
            raise forms.ValidationError("Enter left-side characters to match remarks.")
        return value


class UdinInvTvBulkUpdateForm(forms.Form):
    """Set Inv TV amt on UDIN rows matching client + service (blank Inv TV only)."""

    client = forms.ModelChoiceField(
        label="Client",
        queryset=Client.objects.none(),
        widget=forms.Select(attrs={"class": "input-medium"}),
    )
    service = forms.ModelChoiceField(
        label="Service",
        queryset=Service.objects.none(),
        widget=forms.Select(attrs={"class": "input-medium"}),
    )
    fee_amount = forms.DecimalField(
        label="Inv TV amt",
        max_digits=14,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("client_name", "client_code")
        self.fields["service"].queryset = Service.objects.order_by("service_desc", "service_code")


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


class CertificationPeriodFeeForm(forms.ModelForm):
    class Meta:
        model = CertificationPeriodFee
        fields = ["client", "from_date", "to_date", "fee_amount"]
        labels = {
            "from_date": "From date",
            "to_date": "To date",
            "fee_amount": "Fee (Inv TV amt)",
        }
        widgets = {
            "client": forms.Select(attrs={"class": "input-medium"}),
            "from_date": forms.DateInput(attrs={"type": "date", "class": "input-compact"}),
            "to_date": forms.DateInput(attrs={"type": "date", "class": "input-compact"}),
            "fee_amount": forms.NumberInput(attrs={"class": "input-compact", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("client_name", "client_code")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("from_date")
        end = cleaned.get("to_date")
        client = cleaned.get("client")
        if start and end and start > end:
            raise forms.ValidationError("From date must be on or before To date.")
        if start and end and client:
            overlap = CertificationPeriodFee.objects.filter(
                client=client,
                from_date__lte=end,
                to_date__gte=start,
            )
            if self.instance and self.instance.pk:
                overlap = overlap.exclude(pk=self.instance.pk)
            if overlap.exists():
                raise forms.ValidationError(
                    "This date range overlaps an existing fee period for this client."
                )
        return cleaned


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
