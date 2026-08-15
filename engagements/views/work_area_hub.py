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

from .constants import _WORK_AREA_STATUS_FILTERS

def work_area_hub(request):
    return render(request, "engagements/work_area_hub.html")


@login_required
def work_area_pick_engagement(request):
    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    engagement_items = (
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        )
        .annotate(work_area_count=Count("work_areas"))
        .order_by(
            "client__client_name",
            "fiscal_year__fy_no",
            "service__service_desc",
        )
    )
    if raw_status == "active":
        engagement_items = engagement_items.exclude(status=STATUS_COMPLETED)
    if not request.user.is_superuser:
        engagement_items = engagement_items.exclude(status=STATUS_COMPLETED)
    engagement_items = filter_engagement_queryset(engagement_items, request)
    return render(
        request,
        "engagements/work_area_pick_engagement.html",
        {
            "engagements": engagement_items,
            "work_area_status_filter": raw_status,
        },
    )


@login_required
def work_area_pick_division(request):
    status_val = request.GET.get("status")
    if status_val is None and request.method == "POST":
        status_val = request.POST.get("status")
    raw_status = (status_val or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .annotate(work_area_count=Count("work_areas"))
        .order_by(
            "engagement__client__client_name",
            "engagement__fiscal_year__fy_no",
            "engagement__service__service_desc",
            "division_name",
        )
    )
    if raw_status == "active":
        divisions = divisions.exclude(status=STATUS_COMPLETED)
    divisions = filter_by_engagement_id(divisions, request, "engagement_id")
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "send_confirmation_mail_all":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            sent_divisions = 0
            skipped_divisions = 0
            failed_divisions = 0
            for division in divisions:
                result = team_mail.silent_notify_division_work_area_confirmation_mail(
                    request, division
                )
                if result == "sent":
                    sent_divisions += 1
                elif result == "noop":
                    skipped_divisions += 1
                else:
                    failed_divisions += 1
            if sent_divisions:
                messages.success(
                    request,
                    f"Confirmation mail processed for {sent_divisions} division(s).",
                )
            if skipped_divisions:
                messages.info(
                    request,
                    (
                        f"Skipped {skipped_divisions} division(s) with no pending "
                        "work area assignment confirmations."
                    ),
                )
            if failed_divisions:
                messages.warning(
                    request,
                    f"Could not process confirmation mail for {failed_divisions} division(s).",
                )
            base = reverse("work_area_pick_division")
            if raw_status == "all":
                return redirect(f"{base}?{urlencode({'status': 'all'})}")
            return redirect(base)
    if not request.user.is_superuser:
        divisions = divisions.exclude(engagement__status=STATUS_COMPLETED)
    return render(
        request,
        "engagements/work_area_pick_division.html",
        {
            "divisions": divisions,
            "work_area_status_filter": raw_status,
        },
    )
