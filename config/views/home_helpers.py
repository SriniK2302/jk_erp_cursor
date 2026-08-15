from config.views._std_imports import *  # noqa: F403

from .access import _engagement_queryset_for_user

def _home_work_list_rows(user, request=None):
    """
    Rows for the home work list (engagements the user may access):

    1. Every **open** engagement-level or division-level **schedule line** (period with no
       ``actual_finish``).
    2. Every **engagement-level** and **division-level work area** on **Scheduled** or **In
       progress** engagements that does **not** already have an open schedule line (so
       timers and schedules are reachable even before period rows exist).
    3. A single **engagement** fallback row only when that engagement still has no period
       rows and **no** work areas at all.

    Open period rows are included for any engagement status (as long as the user can see
    the engagement). Bare work-area rows are limited to Scheduled / In progress to avoid
    listing every area on completed engagements.
    """
    import datetime

    from engagements.models import (
        DivisionWorkArea,
        DivisionWorkAreaPeriod,
        EngagementWorkArea,
        EngagementWorkAreaPeriod,
    )

    eng_qs = _engagement_queryset_for_user(user)
    if request is not None:
        from engagements.session_context import filter_engagement_queryset

        eng_qs = filter_engagement_queryset(eng_qs, request, user)
    rows = []
    ew_ids_with_open_period: set[int] = set()
    dw_ids_with_open_period: set[int] = set()

    for p in (
        EngagementWorkAreaPeriod.objects.filter(
            actual_finish__isnull=True,
            work_area__engagement__in=eng_qs,
        )
        .select_related(
            "work_area",
            "work_area__engagement",
            "work_area__engagement__client",
            "work_area__engagement__fiscal_year",
            "work_area__engagement__service",
        )
        .iterator()
    ):
        ew_ids_with_open_period.add(p.work_area_id)
        e = p.work_area.engagement
        sort_date = p.planned_finish or p.planned_start
        rows.append(
            {
                "kind": "ew_period",
                "engagement": e,
                "work_area": p.work_area,
                "label": p.work_area.work_area_name,
                "planned_finish": p.planned_finish,
                "sort_date": sort_date,
                "work_area_sort_key": p.work_area.sort_order,
            }
        )

    for p in (
        DivisionWorkAreaPeriod.objects.filter(
            actual_finish__isnull=True,
            work_area__division__engagement__in=eng_qs,
        )
        .select_related(
            "work_area",
            "work_area__division",
            "work_area__division__engagement",
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
        )
        .iterator()
    ):
        dw_ids_with_open_period.add(p.work_area_id)
        e = p.work_area.division.engagement
        div = p.work_area.division
        sort_date = p.planned_finish or p.planned_start
        rows.append(
            {
                "kind": "dw_period",
                "engagement": e,
                "division": div,
                "work_area": p.work_area,
                "label": f"{div.division_name} · {p.work_area.work_area_name}",
                "planned_finish": p.planned_finish,
                "sort_date": sort_date,
                "work_area_sort_key": p.work_area.sort_order,
            }
        )

    max_sort = datetime.date(9999, 12, 31)
    sched_or_in_progress = eng_qs.filter(
        status__in=[STATUS_SCHEDULED, STATUS_IN_PROGRESS]
    )

    for wa in (
        EngagementWorkArea.objects.filter(engagement__in=sched_or_in_progress)
        .exclude(pk__in=ew_ids_with_open_period)
        .select_related(
            "engagement",
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .iterator()
    ):
        e = wa.engagement
        rows.append(
            {
                "kind": "ew_area",
                "engagement": e,
                "work_area": wa,
                "label": wa.work_area_name,
                "planned_finish": None,
                "sort_date": max_sort,
                "work_area_sort_key": wa.sort_order,
            }
        )

    for wa in (
        DivisionWorkArea.objects.filter(division__engagement__in=sched_or_in_progress)
        .exclude(pk__in=dw_ids_with_open_period)
        .select_related(
            "division",
            "division__engagement",
            "division__engagement__client",
            "division__engagement__fiscal_year",
            "division__engagement__service",
        )
        .iterator()
    ):
        div = wa.division
        e = div.engagement
        rows.append(
            {
                "kind": "dw_area",
                "engagement": e,
                "division": div,
                "work_area": wa,
                "label": f"{div.division_name} · {wa.work_area_name}",
                "planned_finish": None,
                "sort_date": max_sort,
                "work_area_sort_key": wa.sort_order,
            }
        )

    covered_engagement_ids = {r["engagement"].pk for r in rows}

    for eng in (
        sched_or_in_progress.annotate(
            earliest_planned_finish=Min("schedules__planned_finish")
        ).select_related("client", "fiscal_year", "service")
    ):
        if eng.pk in covered_engagement_ids:
            continue
        sort_date = eng.earliest_planned_finish
        rows.append(
            {
                "kind": "engagement",
                "engagement": eng,
                "label": "Engagement (no work areas yet)",
                "planned_finish": eng.earliest_planned_finish,
                "sort_date": sort_date or max_sort,
                "work_area_sort_key": 10_000,
            }
        )

    rows.sort(
        key=lambda r: (
            r["sort_date"] or max_sort,
            r["engagement"].client.client_name,
            r["engagement"].fiscal_year.fy_no,
            r["engagement"].service.service_desc,
            r.get("work_area_sort_key", 0),
            r.get("label") or "",
        )
    )
    return rows

