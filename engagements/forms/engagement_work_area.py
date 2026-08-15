from django import forms
from django.db.models import Max

from engagements.models import EngagementDocumentation, EngagementWorkArea

class EngagementWorkAreaForm(forms.ModelForm):
    class Meta:
        model = EngagementWorkArea
        fields = ["work_area_name", "documentation", "sort_order"]
        widgets = {
            "work_area_name": forms.TextInput(attrs={"class": "input-medium"}),
            "documentation": forms.Select(attrs={"class": "input-medium"}),
            "sort_order": forms.NumberInput(attrs={"class": "input-compact"}),
        }

    def __init__(self, *args, engagement=None, **kwargs):
        self.engagement = engagement
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
            engagement is not None
            and not self.is_bound
            and not getattr(self.instance, "pk", None)
            and self.fields["sort_order"].initial in (None, "", 0)
        ):
            max_order = (
                EngagementWorkArea.objects.filter(engagement=engagement).aggregate(
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
        engagement = self.engagement
        if engagement is None and self.instance.pk:
            engagement = self.instance.engagement
        if not name or engagement is None:
            return cleaned_data

        duplicates = EngagementWorkArea.objects.filter(
            engagement=engagement,
            work_area_name=name,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "work_area_name",
                "This work area name already exists for the engagement.",
            )
        return cleaned_data
