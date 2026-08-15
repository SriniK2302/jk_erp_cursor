from django import forms
from django.urls import reverse

from config.widgets import TeamMemberPickerWidget
from engagements.models import (
    EngagementDivisionDocumentationMap,
    EngagementDocumentation,
)

from .documentation_helpers import (
    _documentation_choice_label,
    filter_engagement_documentation_by_client_classification,
)

class EngagementDivisionDocumentationMapForm(forms.ModelForm):
    class Meta:
        model = EngagementDivisionDocumentationMap
        fields = ["documentation"]
        widgets = {
            "documentation": forms.Select(attrs={"class": "input-long"}),
        }

    def __init__(self, *args, **kwargs):
        self.division = kwargs.pop("division", None)
        super().__init__(*args, **kwargs)
        base_queryset = (
            self.fields["documentation"]
            .queryset.prefetch_related("applicable_classifications")
            .order_by("document_stage", "standard_document")
        )
        division = self.division or getattr(self.instance, "division", None)
        if division is not None:
            used_doc_ids_qs = EngagementDivisionDocumentationMap.objects.filter(
                division=division
            )
            if self.instance and self.instance.pk and self.instance.documentation_id:
                used_doc_ids_qs = used_doc_ids_qs.exclude(
                    documentation_id=self.instance.documentation_id
                )
            base_queryset = base_queryset.exclude(
                pk__in=used_doc_ids_qs.values_list("documentation_id", flat=True)
            )
            include_pk = None
            if self.instance and self.instance.pk and self.instance.documentation_id:
                include_pk = self.instance.documentation_id
            base_queryset = filter_engagement_documentation_by_client_classification(
                base_queryset,
                division.engagement.client,
                include_documentation_pk=include_pk,
            )

        initial_id = ""
        initial_label = ""
        if self.instance and self.instance.pk and self.instance.documentation_id:
            initial_id = str(self.instance.documentation_id)
            initial_label = _documentation_choice_label(self.instance.documentation)
            self.fields["documentation"].queryset = base_queryset
            self.fields["documentation"].label_from_instance = _documentation_choice_label
        else:
            self.fields["documentation"] = forms.ModelMultipleChoiceField(
                queryset=base_queryset,
                required=True,
                label="Documentation",
            )
            self.fields["documentation"].label_from_instance = _documentation_choice_label

        tid = (self.auto_id % "documentation") if self.auto_id else "documentation"
        search_url = (
            reverse(
                "engagement_division_documentation_option_search",
                kwargs={"division_pk": division.pk},
            )
            if division is not None
            else ""
        )
        self.fields["documentation"].widget = TeamMemberPickerWidget(
            attrs={
                "id": tid,
                "data_search_url": search_url,
                "data_for_user": initial_id,
                "data_multiple": "0" if initial_id else "1",
                "data_initial_ids": "",
                "data_search_placeholder": "Search documentation...",
                "data_search_aria": "Search documentation",
                "data_search_help": (
                    "Type to search documentation. Results are limited to items whose "
                    "Applicable To includes this engagement client's classification; "
                    "already mapped items are excluded (except the current item when editing)."
                ),
                "data_clear_label": "Clear documentation link",
                "data_empty_text": "No documentation matches.",
                "data_error_text": "Could not load documentation results.",
                "data_initial_id": initial_id,
                "data_initial_label": initial_label,
            }
        )

    def clean_documentation(self):
        documentation = self.cleaned_data.get("documentation")
        division = self.division or getattr(self.instance, "division", None)
        if documentation is None or division is None:
            return documentation

        docs = (
            list(documentation)
            if hasattr(documentation, "__iter__")
            and not isinstance(documentation, EngagementDocumentation)
            else [documentation]
        )
        cl = division.engagement.client.classification
        for doc in docs:
            if not doc.applicable_classifications.filter(pk=cl.pk).exists():
                raise forms.ValidationError(
                    "Each selected item must list this engagement client's classification "
                    f"under Applicable To ({cl.classification_name})."
                )
        duplicate_exists = EngagementDivisionDocumentationMap.objects.filter(
            division=division,
            documentation__in=docs,
        )
        if self.instance and self.instance.pk:
            duplicate_exists = duplicate_exists.exclude(pk=self.instance.pk)
        if duplicate_exists.exists():
            raise forms.ValidationError(
                "One or more selected documentation items are already mapped to the division."
            )
        return documentation

    def _post_clean(self):
        # Create mode uses ModelMultipleChoiceField for "documentation". Skip model binding
        # in ModelForm._post_clean because model FK expects a single instance.
        if (
            self.instance is not None
            and self.instance.pk is None
            and isinstance(
                self.fields.get("documentation"),
                forms.ModelMultipleChoiceField,
            )
        ):
            return
        super()._post_clean()
