from django.db.models import Q

from engagements.models import EngagementDocumentation

def _documentation_choice_label(item: EngagementDocumentation) -> str:
    names = ", ".join(
        c.classification_name
        for c in sorted(
            item.applicable_classifications.all(),
            key=lambda c: c.classification_name,
        )
    )
    return (
        f"{item.standard_document} "
        f"({item.get_document_stage_display()} - {names})"
    )


def filter_engagement_documentation_by_client_classification(
    queryset,
    client,
    *,
    include_documentation_pk=None,
):
    """Keep setup documentation rows whose Applicable To includes the client's classification."""
    classification = getattr(client, "classification", None)
    if classification is None:
        return queryset.none()
    q = Q(applicable_classifications=classification)
    if include_documentation_pk:
        q |= Q(pk=include_documentation_pk)
    return queryset.filter(q).distinct()
