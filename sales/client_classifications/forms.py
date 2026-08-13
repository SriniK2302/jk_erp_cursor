from django import forms

from .models import ClientClassification


class ClientClassificationForm(forms.ModelForm):
    class Meta:
        model = ClientClassification
        fields = ["classification_name"]
        widgets = {
            "classification_name": forms.TextInput(attrs={"class": "input-medium"}),
        }

    def clean_classification_name(self):
        classification_name = (self.cleaned_data.get("classification_name") or "").strip()
        if not classification_name:
            raise forms.ValidationError("Client classification is required.")
        return classification_name
