from django import forms

from sales.clients.models import Client
from sales.services.models import Service


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
