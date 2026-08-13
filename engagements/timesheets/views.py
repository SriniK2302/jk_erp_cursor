from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from hr.teams.models import TeamMember

from .. import views as engagement_views
from ..session_context import get_session_engagement
from ..closure import (
    assert_division_open_for_management,
    assert_engagement_open_for_management,
)
from .models import (
    TIME_SESSION_CLOSE_SOURCE_AUTO_SWITCH,
    TIME_SESSION_CLOSE_SOURCE_USER_STOP,
    TIME_SESSION_STATUS_CLOSED,
    TIME_SESSION_STATUS_OPEN,
    TimeSession,
)
from .timer_support import distinct_task_labels_for_scope

_TIME_LOG_RANGE_KEYS = frozenset({"today", "week", "all"})
_TASK_DESC_MAX_LEN = 500


def _session_target_equals(
    session,
    *,
    engagement_id,
    division_id=None,
    engagement_work_area_id=None,
    division_work_area_id=None,
):
    if session is None:
        return False
    return (
        session.engagement_id == engagement_id
        and session.division_id == division_id
        and session.engagement_work_area_id == engagement_work_area_id
        and session.division_work_area_id == division_work_area_id
    )


def _resolve_next_url(request, fallback_url):
    nxt = (request.POST.get("next") or "").strip()
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return nxt
    return fallback_url


def _clean_task_description(request) -> str:
    raw = (request.POST.get("task") or "").replace("\r\n", "\n").replace("\r", "\n")
    collapsed = " ".join(raw.split())
    return collapsed.strip()[:_TASK_DESC_MAX_LEN]


def _parse_optional_positive_int(val) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s.isdigit():
        return None
    n = int(s)
    return n if n > 0 else None


def _close_session(session, *, ended_at, close_source):
    if session is None:
        return
    session.ended_at = ended_at
    session.duration_minutes = max(0, int((ended_at - session.started_at).total_seconds() // 60))
    session.status = TIME_SESSION_STATUS_CLOSED
    session.close_source = close_source
    session.save(
        update_fields=[
            "ended_at",
            "duration_minutes",
            "status",
            "close_source",
            "task_description",
            "updated_on",
        ]
    )


def _start_session_for_target(
    request,
    *,
    engagement,
    division=None,
    engagement_work_area=None,
    division_work_area=None,
):
    team_member = TeamMember.objects.filter(user=request.user).first()
    if team_member is None:
        messages.error(request, "Set up Team Member for this user before starting timer.")
        return False

    task_description = _clean_task_description(request)
    now = timezone.now()
    with transaction.atomic():
        open_session = (
            TimeSession.objects.select_for_update()
            .filter(started_by=request.user, ended_at__isnull=True)
            .order_by("-started_at", "-id")
            .first()
        )
        if _session_target_equals(
            open_session,
            engagement_id=engagement.pk,
            division_id=division.pk if division else None,
            engagement_work_area_id=engagement_work_area.pk if engagement_work_area else None,
            division_work_area_id=division_work_area.pk if division_work_area else None,
        ):
            messages.info(request, "Timer is already running for this item.")
            return False

        if open_session is not None:
            _close_session(
                open_session,
                ended_at=now,
                close_source=TIME_SESSION_CLOSE_SOURCE_AUTO_SWITCH,
            )
            messages.info(request, "Closed previous timer and switched to new item.")

        TimeSession.objects.create(
            team_member=team_member,
            started_by=request.user,
            engagement=engagement,
            division=division,
            engagement_work_area=engagement_work_area,
            division_work_area=division_work_area,
            started_at=now,
            status=TIME_SESSION_STATUS_OPEN,
            close_source="",
            task_description=task_description,
        )
    messages.success(request, "Timer started.")
    return True


@login_required
@require_POST
def timer_stop(request):
    fallback_url = reverse("my_time_log")
    with transaction.atomic():
        open_session = (
            TimeSession.objects.select_for_update()
            .filter(started_by=request.user, ended_at__isnull=True)
            .order_by("-started_at", "-id")
            .first()
        )
        if open_session is None:
            messages.info(request, "No active timer to stop.")
        else:
            task_text = _clean_task_description(request)
            if task_text:
                open_session.task_description = task_text
                open_session.save(update_fields=["task_description", "updated_on"])
            _close_session(
                open_session,
                ended_at=timezone.now(),
                close_source=TIME_SESSION_CLOSE_SOURCE_USER_STOP,
            )
            messages.success(request, "Timer stopped.")
    return redirect(_resolve_next_url(request, fallback_url))


@login_required
@require_POST
def timer_start_engagement(request, engagement_pk):
    engagement = get_object_or_404(
        engagement_views._engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    _start_session_for_target(request, engagement=engagement)
    return redirect(_resolve_next_url(request, reverse("engagements")))


@login_required
@require_POST
def timer_start_division(request, division_pk):
    division = get_object_or_404(
        engagement_views._engagement_division_queryset_for_user(request.user).select_related(
            "engagement"
        ),
        pk=division_pk,
    )
    assert_division_open_for_management(request.user, division)
    _start_session_for_target(
        request,
        engagement=division.engagement,
        division=division,
    )
    return redirect(_resolve_next_url(request, reverse("engagement_divisions")))


@login_required
@require_POST
def timer_start_engagement_work_area(request, engagement_pk, work_area_pk):
    work_area = get_object_or_404(
        engagement_views._engagement_work_area_queryset_for_user(request.user).select_related(
            "engagement"
        ),
        pk=work_area_pk,
        engagement_id=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, work_area.engagement)
    _start_session_for_target(
        request,
        engagement=work_area.engagement,
        engagement_work_area=work_area,
    )
    return redirect(
        _resolve_next_url(
            request,
            reverse("engagement_work_areas", kwargs={"engagement_pk": engagement_pk}),
        )
    )


@login_required
@require_POST
def timer_start_division_work_area(request, division_pk, work_area_pk):
    work_area = get_object_or_404(
        engagement_views._division_work_area_queryset_for_user(request.user).select_related(
            "division__engagement"
        ),
        pk=work_area_pk,
        division_id=division_pk,
    )
    assert_division_open_for_management(request.user, work_area.division)
    _start_session_for_target(
        request,
        engagement=work_area.division.engagement,
        division=work_area.division,
        division_work_area=work_area,
    )
    return redirect(
        _resolve_next_url(
            request,
            reverse("engagement_division_work_areas", kwargs={"division_pk": division_pk}),
        )
    )


@login_required
@require_GET
def timer_recent_tasks(request):
    if not request.user.is_superuser and not engagement_views._has_engagements_module_access(
        request.user
    ):
        return JsonResponse({"tasks": []}, status=403)

    dwa = _parse_optional_positive_int(request.GET.get("division_work_area"))
    ewa = _parse_optional_positive_int(request.GET.get("engagement_work_area"))
    div = _parse_optional_positive_int(request.GET.get("division"))
    eng = _parse_optional_positive_int(request.GET.get("engagement"))

    if dwa is not None:
        work_area = get_object_or_404(
            engagement_views._division_work_area_queryset_for_user(request.user).select_related(
                "division__engagement"
            ),
            pk=dwa,
        )
        labels = distinct_task_labels_for_scope(
            request.user,
            engagement_id=work_area.division.engagement_id,
            division_id=work_area.division_id,
            division_work_area_id=work_area.pk,
        )
    elif ewa is not None:
        work_area = get_object_or_404(
            engagement_views._engagement_work_area_queryset_for_user(request.user).select_related(
                "engagement"
            ),
            pk=ewa,
        )
        labels = distinct_task_labels_for_scope(
            request.user,
            engagement_id=work_area.engagement_id,
            engagement_work_area_id=work_area.pk,
        )
    elif div is not None:
        division = get_object_or_404(
            engagement_views._engagement_division_queryset_for_user(request.user).select_related(
                "engagement"
            ),
            pk=div,
        )
        labels = distinct_task_labels_for_scope(
            request.user,
            engagement_id=division.engagement_id,
            division_id=division.pk,
        )
    elif eng is not None:
        get_object_or_404(engagement_views._engagement_queryset_for_user(request.user), pk=eng)
        labels = distinct_task_labels_for_scope(request.user, engagement_id=eng)
    else:
        return JsonResponse({"error": "Missing scope"}, status=400)

    return JsonResponse({"tasks": labels})


@login_required
@require_GET
def my_time_log(request):
    if not request.user.is_superuser and not engagement_views._has_engagements_module_access(
        request.user
    ):
        raise PermissionDenied("Engagements module access is required.")

    range_key = (request.GET.get("range") or "week").strip().lower()
    if range_key not in _TIME_LOG_RANGE_KEYS:
        range_key = "week"

    qs = (
        TimeSession.objects.filter(started_by=request.user)
        .select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
            "division",
            "engagement_work_area",
            "division_work_area",
        )
        .order_by("-started_at", "-id")
    )
    if not request.user.is_superuser:
        qs = qs.filter(
            engagement_id__in=engagement_views._engagement_queryset_for_user(request.user)
        )

    today = timezone.localdate()
    if range_key == "today":
        qs = qs.filter(started_at__date=today)
    elif range_key == "week":
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=7)
        qs = qs.filter(started_at__date__gte=week_start, started_at__date__lt=week_end)

    engagement_filter = ""
    engagement_filter_pk = None
    raw_eng = (request.GET.get("engagement") or "").strip()
    if raw_eng.isdigit():
        eid = int(raw_eng)
        if engagement_views._engagement_queryset_for_user(request.user).filter(pk=eid).exists():
            qs = qs.filter(engagement_id=eid)
            engagement_filter = str(eid)
            engagement_filter_pk = eid
    else:
        session_engagement = get_session_engagement(request)
        if session_engagement is not None:
            qs = qs.filter(engagement_id=session_engagement.pk)
            engagement_filter = str(session_engagement.pk)
            engagement_filter_pk = session_engagement.pk

    engagement_choices = engagement_views._engagement_queryset_for_user(request.user).select_related(
        "client",
        "fiscal_year",
        "service",
    ).order_by("client__client_name", "fiscal_year__fy_no", "service__service_desc")

    candidate = list(qs[:501])
    truncated = len(candidate) > 500
    sessions_list = candidate[:500]

    now = timezone.now()
    rows = []
    for session in sessions_list:
        if session.ended_at:
            display_minutes = session.duration_minutes
            row_status = "Closed"
        else:
            display_minutes = max(0, int((now - session.started_at).total_seconds() // 60))
            row_status = "Running"
        scope_parts = [
            session.engagement.client.display_name,
            session.engagement.fiscal_year.fy_no,
            session.engagement.service.service_desc,
        ]
        if session.division_id:
            scope_parts.append(session.division.division_name)
        if session.engagement_work_area_id:
            scope_parts.append(session.engagement_work_area.work_area_name)
        if session.division_work_area_id:
            scope_parts.append(session.division_work_area.work_area_name)
        rows.append(
            {
                "session": session,
                "display_minutes": display_minutes,
                "row_status": row_status,
                "scope_label": " · ".join(scope_parts),
            }
        )
    total_minutes = sum(r["display_minutes"] for r in rows)
    total_hours = total_minutes / 60.0 if total_minutes else 0.0

    query_base = {}
    if engagement_filter:
        query_base["engagement"] = engagement_filter

    def _range_url(key: str) -> str:
        q = {**query_base, "range": key}
        return f"{reverse('my_time_log')}?{urlencode(q)}"

    return render(
        request,
        "engagements/my_time_log.html",
        {
            "rows": rows,
            "range_key": range_key,
            "engagement_filter": engagement_filter,
            "engagement_filter_pk": engagement_filter_pk,
            "engagement_choices": engagement_choices,
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "url_today": _range_url("today"),
            "url_week": _range_url("week"),
            "url_all": _range_url("all"),
            "truncated": truncated,
        },
    )
