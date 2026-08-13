"""Remove engagement/division documentation maps when setup doc no longer applies."""

from django.db.models import Count

from engagements.models import (
    EngagementDivisionDocumentationMap,
    EngagementDocumentationMap,
)


def delete_maps_for_removed_setup_classifications(documentation, removed_classification_ids):
    """
    When ``EngagementDocumentation.applicable_classifications`` loses one or more
    classifications, drop maps for engagements whose *client* had one of those
    classifications, only if the map has no uploaded attachments.

    Returns counts for UI messaging.
    """
    removed = {int(x) for x in (removed_classification_ids or ())}
    if not removed or not getattr(documentation, "pk", None):
        return {
            "engagement_deleted": 0,
            "division_deleted": 0,
            "engagement_blocked": 0,
            "division_blocked": 0,
        }

    cid_list = list(removed)

    eng_annotated = EngagementDocumentationMap.objects.filter(
        documentation_id=documentation.pk,
        engagement__client__classification_id__in=cid_list,
    ).annotate(_att=Count("attachments"))

    div_annotated = EngagementDivisionDocumentationMap.objects.filter(
        documentation_id=documentation.pk,
        division__engagement__client__classification_id__in=cid_list,
    ).annotate(_att=Count("attachments"))

    engagement_blocked = eng_annotated.filter(_att__gt=0).count()
    division_blocked = div_annotated.filter(_att__gt=0).count()

    eng_deletable = eng_annotated.filter(_att=0)
    div_deletable = div_annotated.filter(_att=0)

    n_eng = eng_deletable.count()
    n_div = div_deletable.count()

    eng_deletable.delete()
    div_deletable.delete()

    return {
        "engagement_deleted": n_eng,
        "division_deleted": n_div,
        "engagement_blocked": engagement_blocked,
        "division_blocked": division_blocked,
    }


def notify_documentation_map_cascade(request, summary):
    """Flash messages after setup documentation classifications are narrowed."""
    if request is None:
        return
    from django.contrib import messages

    ed = summary["engagement_deleted"]
    dd = summary["division_deleted"]
    eb = summary["engagement_blocked"]
    db = summary["division_blocked"]
    if ed or dd:
        messages.success(
            request,
            (
                f"Removed {ed} engagement-level and {dd} division-level documentation mapping(s) "
                "for clients whose classification was removed from Applicable To, "
                "only where no file had been uploaded for that mapping."
            ),
        )
    if eb or db:
        messages.warning(
            request,
            (
                f"Kept {eb} engagement-level and {db} division-level mapping(s) that still have "
                "uploaded files; remove or reclassify those in the engagement screens if needed."
            ),
        )
