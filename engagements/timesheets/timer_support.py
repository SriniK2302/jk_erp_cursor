"""Helpers for timer / time-session task scoping."""

from django.db.utils import OperationalError, ProgrammingError

from .models import TimeSession


def distinct_task_labels_for_scope(
    user,
    *,
    engagement_id: int,
    division_id: int | None = None,
    engagement_work_area_id: int | None = None,
    division_work_area_id: int | None = None,
    limit: int = 20,
) -> list[str]:
    """Recent non-empty task text for the exact timer scope (engagement / division / work area)."""
    fl: dict = {"started_by": user, "engagement_id": engagement_id}
    if division_work_area_id is not None:
        fl["division_id"] = division_id
        fl["division_work_area_id"] = division_work_area_id
        fl["engagement_work_area_id__isnull"] = True
    elif engagement_work_area_id is not None:
        fl["engagement_work_area_id"] = engagement_work_area_id
        fl["division_id__isnull"] = True
        fl["division_work_area_id__isnull"] = True
    elif division_id is not None:
        fl["division_id"] = division_id
        fl["engagement_work_area_id__isnull"] = True
        fl["division_work_area_id__isnull"] = True
    else:
        fl["division_id__isnull"] = True
        fl["engagement_work_area_id__isnull"] = True
        fl["division_work_area_id__isnull"] = True

    try:
        rows = (
            TimeSession.objects.filter(**fl)
            .exclude(task_description="")
            .order_by("-started_at", "-id")[:120]
            .values_list("task_description", flat=True)
        )
        seen: set[str] = set()
        out: list[str] = []
        for raw in rows:
            t = (raw or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= limit:
                break
        return out
    except (OperationalError, ProgrammingError):
        return []
