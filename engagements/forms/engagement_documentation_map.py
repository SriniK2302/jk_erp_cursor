from django import forms
from django.urls import reverse
from django.utils import timezone

from config.widgets import TeamMemberPickerWidget
from engagements.models import (
    EngagementDocumentation,
    EngagementDocumentationMap,
)

from .documentation_helpers import (
    _documentation_choice_label,
    filter_engagement_documentation_by_client_classification,
)

class EngagementDocumentationMapForm(forms.ModelForm):
    class Meta:
        model = EngagementDocumentationMap
        fields = ["documentation", "documentation_date"]
        widgets = {
            "documentation": forms.Select(attrs={"class": "input-long"}),
            "documentation_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.engagement = kwargs.pop("engagement", None)
        super().__init__(*args, **kwargs)
        base_queryset = (
            self.fields["documentation"]
            .queryset.prefetch_related("applicable_classifications")
            .order_by("document_stage", "standard_document")
        )
        engagement = self.engagement or getattr(self.instance, "engagement", None)
        if engagement is not None:
            used_doc_ids_qs = EngagementDocumentationMap.objects.filter(
                engagement=engagement
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
                engagement.client,
                include_documentation_pk=include_pk,
            )

        if not (self.instance and self.instance.pk):
            self.fields["documentation_date"].initial = timezone.localdate()

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
                "engagement_documentation_option_search",
                kwargs={"engagement_pk": engagement.pk},
            )
            if engagement is not None
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
                    "Applicable To includes this client's classification; already mapped "
                    "items are excluded (except the current item when editing)."
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
        engagement = self.engagement or getattr(self.instance, "engagement", None)
        if documentation is None or engagement is None:
            return documentation

        docs = (
            list(documentation)
            if hasattr(documentation, "__iter__")
            and not isinstance(documentation, EngagementDocumentation)
            else [documentation]
        )
        cl = engagement.client.classification
        for doc in docs:
            if not doc.applicable_classifications.filter(pk=cl.pk).exists():
                raise forms.ValidationError(
                    "Each selected item must list this client's classification under "
                    f"Applicable To ({cl.classification_name})."
                )
        duplicate_exists = EngagementDocumentationMap.objects.filter(
            engagement=engagement,
            documentation__in=docs,
        )
        if self.instance and self.instance.pk:
            duplicate_exists = duplicate_exists.exclude(pk=self.instance.pk)
        if duplicate_exists.exists():
            raise forms.ValidationError(
                "One or more selected documentation items are already mapped to the engagement."
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
