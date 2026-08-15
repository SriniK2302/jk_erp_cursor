from django import forms
from django.db.models import Max

from engagements.models import DivisionWorkArea, EngagementDocumentation

class DivisionWorkAreaForm(forms.ModelForm):
    class Meta:
        model = DivisionWorkArea
        fields = ["work_area_name", "documentation", "sort_order"]
        widgets = {
            "work_area_name": forms.TextInput(attrs={"class": "input-medium"}),
            "documentation": forms.Select(attrs={"class": "input-medium"}),
            "sort_order": forms.NumberInput(attrs={"class": "input-compact"}),
        }

    def __init__(self, *args, division=None, **kwargs):
        self.division = division
        super().__init__(*args, **kwargs)
        self.fields["documentation"].queryset = EngagementDocumentation.objects.order_by(
            "standard_document", "document_stage"
        )
        self.fields["documentation"].required = True
        self.fields["documentation"].empty_label = "— Select documentation —"
        self.fields["documentation"].label_from_instance = (
            lambda obj: f"{obj.standard_document} ({obj.get_document_stage_display()})"
        )
        if (
            division is not None
            and not self.is_bound
            and not getattr(self.instance, "pk", None)
            and self.fields["sort_order"].initial in (None, "", 0)
        ):
            max_order = (
                DivisionWorkArea.objects.filter(division=division).aggregate(
                    max_order=Max("sort_order")
                )["max_order"]
                or 0
            )
            self.fields["sort_order"].initial = max_order + 1

    def clean_work_area_name(self):
        name = (self.cleaned_data.get("work_area_name") or "").strip()
        if not name:
            raise forms.ValidationError("Work area name is required.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("work_area_name")
        division = self.division
        if division is None and self.instance.pk:
            division = self.instance.division
        if not name or division is None:
            return cleaned_data

        duplicates = DivisionWorkArea.objects.filter(
            division=division,
            work_area_name=name,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "work_area_name",
                "This work area name already exists for the division.",
            )
        return cleaned_data
