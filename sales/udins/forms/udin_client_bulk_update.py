from django import forms

from sales.clients.models import Client


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
