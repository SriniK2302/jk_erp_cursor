from django import forms

from sales.clients.models import Client

from sales.udins.models import CertificationPeriodFee


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
