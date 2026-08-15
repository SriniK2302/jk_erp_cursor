from engagements.views._std_imports import *  # noqa: F403

from .access import (
    _active_time_session_for_user,
    _can_manage_structure,
    _division_work_area_queryset_for_user,
    _engagement_division_queryset_for_user,
    _engagement_queryset_for_user,
    _engagement_work_area_queryset_for_user,
    _has_engagements_module_access,
    _timer_scope_dict,
)

from .constants import _ENGAGEMENT_LIST_STATUS_FILTERS

def engagements(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            engagement = get_object_or_404(
                _engagement_queryset_for_user(request.user),
                pk=request.POST.get("pk"),
            )
            engagement.delete()
            ret = (request.POST.get("return_status") or "active").strip().lower()
            if ret not in _ENGAGEMENT_LIST_STATUS_FILTERS:
                ret = "active"
            return redirect(f"{reverse('engagements')}?{urlencode({'status': ret})}")
        return redirect("engagements")

    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _ENGAGEMENT_LIST_STATUS_FILTERS:
        raw_status = "active"

    engagement_items = (
        _engagement_queryset_for_user(request.user)
        .select_related("client", "fiscal_year", "service")
        .annotate(
            schedule_count=Count("schedules", distinct=True),
            documentation_count=Count("documentation_maps", distinct=True),
            status_remark_count=Count("status_remarks", distinct=True),
            _work_areas_eng=Count("work_areas", distinct=True),
            _work_areas_div=Count("divisions__work_areas", distinct=True),
            _team_eng=Count("team_assignments", distinct=True),
            _team_div=Count("divisions__team_assignments", distinct=True),
            _team_ewa=Count("work_areas__team_assignments", distinct=True),
            _team_dwa=Count("divisions__work_areas__team_assignments", distinct=True),
        )
        .annotate(
            work_area_count=F("_work_areas_eng") + F("_work_areas_div"),
            team_assignment_count=F("_team_eng")
            + F("_team_div")
            + F("_team_ewa")
            + F("_team_dwa"),
        )
        .order_by(
            "client__client_name",
            "fiscal_year__fy_no",
            "service__service_desc",
        )
    )
    if raw_status == "active":
        engagement_items = engagement_items.exclude(status=STATUS_COMPLETED)
    elif raw_status == "pending":
        engagement_items = engagement_items.filter(
            Q(status=STATUS_PENDING) | Q(status="")
        )
    elif raw_status == "scheduled":
        engagement_items = engagement_items.filter(status=STATUS_SCHEDULED)
    elif raw_status == "in_progress":
        engagement_items = engagement_items.filter(status=STATUS_IN_PROGRESS)
    elif raw_status == "completed":
        engagement_items = engagement_items.filter(status=STATUS_COMPLETED)
    # "all" — no extra filter
    engagement_items = filter_engagement_queryset(engagement_items, request)

    return render(
        request,
        "engagements/engagements.html",
        {
            "engagements": engagement_items,
            "engagement_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
        },
    )

