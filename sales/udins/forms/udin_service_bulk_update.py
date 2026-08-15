from django import forms

from sales.services.models import Service


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
