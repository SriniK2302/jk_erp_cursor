from django import forms
from django.utils import timezone

from sales.invoices.models import Invoice


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "narration",
            "invoice_date",
            "invoice_no",
            "fiscal_year",
            "status",
        ]
        labels = {
            "narration": "Invoice narration",
            "invoice_no": "Inv No",
            "status": "Status",
        }
        help_texts = {
            "status": (
                "Fresh: not yet posted to GL. Use the invoice list "
                "\"Authorise selected & post to GL\" to create an Authorised journal. "
                "You can also set Authorised manually if needed."
            ),
        }
        widgets = {
            "narration": forms.Textarea(
                attrs={
                    "class": "invoice-narration-input",
                    "rows": 2,
                    "placeholder": "Optional — printed once on the bill (before UDIN lines).",
                    "autocomplete": "off",
                }
            ),
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "invoice_no": forms.TextInput(
                attrs={
                    "placeholder": "e.g. FY27-SVSM-001 (suggested, editable)",
                    "autocomplete": "off",
                }
            ),
            "status": forms.Select(attrs={"class": "input-medium"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fiscal_year"].label_from_instance = lambda fy: fy.fy_no
        if not self.data and not self.instance.pk:
            self.fields["invoice_date"].initial = timezone.localdate()

    def clean_narration(self):
        return (self.cleaned_data.get("narration") or "").strip()
