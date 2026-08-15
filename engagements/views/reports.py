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

from .constants import (
    _AUDIT_QUERY_EXPECTED_FILTERS,
    _AUDIT_QUERY_STATUS_FILTERS,
    _AUDIT_QUERY_TYPE_FILTERS,
    _STATUS_REMARK_REPORT_LEVEL_FILTERS,
    _TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS,
)
from .note_mail_helpers import _audit_query_mail_context, _build_note_mailto_url

def _team_assignment_report_rows(user, status_filter="current", engagement_ids=None):
    """Flatten team assignments under engagements visible to user (same scope as engagement list)."""
    status_filter = (status_filter or "current").strip().lower()
    if status_filter not in _TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS:
        status_filter = "current"

    def include_row(is_closed):
        if status_filter == "completed":
            return is_closed
        return not is_closed

    if engagement_ids is None:
        engagement_ids = list(
            _engagement_queryset_for_user(user).values_list("pk", flat=True)
        )
    if not engagement_ids:
        return []

    rows = []

    for a in (
        EngagementTeamAssignment.objects.filter(engagement_id__in=engagement_ids)
        .select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
            "team_member",
        )
        .order_by("id")
    ):
        e = a.engagement
        is_closed = e.status == STATUS_COMPLETED
        if not include_row(is_closed):
            continue
        rows.append(
            {
                "scope": "Engagement",
                "client_name": e.client.display_name,
                "fy_no": e.fiscal_year.fy_no,
                "service_desc": e.service.service_desc,
                "division_name": "—",
                "work_area_name": "—",
                "team_member": str(a.team_member),
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "_sk": (
                    e.client.display_name,
                    e.fiscal_year.fy_no,
                    e.service.service_desc,
                    0,
                    "",
                    "",
                    a.team_member.code,
                    a.pk,
                ),
            }
        )

    for a in (
        EngagementDivisionTeamAssignment.objects.filter(
            division__engagement_id__in=engagement_ids
        )
        .select_related(
            "division__engagement__client",
            "division__engagement__fiscal_year",
            "division__engagement__service",
            "division",
            "team_member",
        )
        .order_by("id")
    ):
        d = a.division
        e = d.engagement
        is_closed = e.status == STATUS_COMPLETED or d.status == STATUS_COMPLETED
        if not include_row(is_closed):
            continue
        rows.append(
            {
                "scope": "Division",
                "client_name": e.client.display_name,
                "fy_no": e.fiscal_year.fy_no,
                "service_desc": e.service.service_desc,
                "division_name": d.division_name,
                "work_area_name": "—",
                "team_member": str(a.team_member),
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "_sk": (
                    e.client.display_name,
                    e.fiscal_year.fy_no,
                    e.service.service_desc,
                    1,
                    d.division_name,
                    "",
                    a.team_member.code,
                    a.pk,
                ),
            }
        )

    for a in (
        EngagementWorkAreaTeamAssignment.objects.filter(
            work_area__engagement_id__in=engagement_ids
        )
        .select_related(
            "work_area__engagement__client",
            "work_area__engagement__fiscal_year",
            "work_area__engagement__service",
            "work_area",
            "team_member",
        )
        .order_by("id")
    ):
        wa = a.work_area
        e = wa.engagement
        is_closed = e.status == STATUS_COMPLETED or wa.status == STATUS_COMPLETED
        if not include_row(is_closed):
            continue
        rows.append(
            {
                "scope": "Eng. work area",
                "client_name": e.client.display_name,
                "fy_no": e.fiscal_year.fy_no,
                "service_desc": e.service.service_desc,
                "division_name": "—",
                "work_area_name": wa.work_area_name,
                "team_member": str(a.team_member),
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "_sk": (
                    e.client.display_name,
                    e.fiscal_year.fy_no,
                    e.service.service_desc,
                    2,
                    "",
                    wa.work_area_name,
                    a.team_member.code,
                    a.pk,
                ),
            }
        )

    for a in (
        DivisionWorkAreaTeamAssignment.objects.filter(
            work_area__division__engagement_id__in=engagement_ids
        )
        .select_related(
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
            "work_area__division",
            "work_area",
            "team_member",
        )
        .order_by("id")
    ):
        wa = a.work_area
        d = wa.division
        e = d.engagement
        is_closed = (
            e.status == STATUS_COMPLETED
            or d.status == STATUS_COMPLETED
            or wa.status == STATUS_COMPLETED
        )
        if not include_row(is_closed):
            continue
        rows.append(
            {
                "scope": "Div. work area",
                "client_name": e.client.display_name,
                "fy_no": e.fiscal_year.fy_no,
                "service_desc": e.service.service_desc,
                "division_name": d.division_name,
                "work_area_name": wa.work_area_name,
                "team_member": str(a.team_member),
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "_sk": (
                    e.client.display_name,
                    e.fiscal_year.fy_no,
                    e.service.service_desc,
                    3,
                    d.division_name,
                    wa.work_area_name,
                    a.team_member.code,
                    a.pk,
                ),
            }
        )

    rows.sort(key=lambda r: r["_sk"])
    for r in rows:
        del r["_sk"]
    return rows


@login_required
def team_assignments_report(request):
    raw_status = (request.GET.get("status") or "current").strip().lower()
    if raw_status not in _TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS:
        raw_status = "current"
    rows = _team_assignment_report_rows(
        request.user,
        status_filter=raw_status,
        engagement_ids=engagement_ids_for_lists(request.user, request),
    )
    return render(
        request,
        "engagements/team_assignments_report.html",
        {
            "rows": rows,
            "assignment_status_filter": raw_status,
        },
    )


def _status_remark_report_rows(user, level_filter="all", engagement_ids=None):
    level_filter = (level_filter or "all").strip().lower()
    if level_filter not in _STATUS_REMARK_REPORT_LEVEL_FILTERS:
        level_filter = "all"

    def include_level(level_name):
        return level_filter == "all" or level_filter == level_name

    if engagement_ids is None:
        engagement_ids = list(
            _engagement_queryset_for_user(user).values_list("pk", flat=True)
        )
    if not engagement_ids:
        return []

    rows = []

    if include_level("engagement"):
        for item in (
            EngagementStatusRemark.objects.filter(engagement_id__in=engagement_ids)
            .select_related(
                "engagement__client",
                "engagement__fiscal_year",
                "engagement__service",
                "created_by",
            )
            .order_by("id")
        ):
            e = item.engagement
            rows.append(
                {
                    "scope": "Engagement",
                    "client_name": e.client.display_name,
                    "fy_no": e.fiscal_year.fy_no,
                    "service_desc": e.service.service_desc,
                    "division_name": "—",
                    "work_area_name": "—",
                    "remark_date": item.remark_date,
                    "remarks": item.remarks,
                    "created_by": str(item.created_by),
                    "created_on": item.created_on,
                    "_sk": (
                        e.client.display_name,
                        e.fiscal_year.fy_no,
                        e.service.service_desc,
                        item.remark_date or timezone.localdate(),
                        0,
                        "",
                        "",
                        item.pk,
                    ),
                }
            )

    if include_level("division"):
        for item in (
            EngagementDivisionStatusRemark.objects.filter(
                division__engagement_id__in=engagement_ids
            )
            .select_related(
                "division__engagement__client",
                "division__engagement__fiscal_year",
                "division__engagement__service",
                "created_by",
            )
            .order_by("id")
        ):
            d = item.division
            e = d.engagement
            rows.append(
                {
                    "scope": "Division",
                    "client_name": e.client.display_name,
                    "fy_no": e.fiscal_year.fy_no,
                    "service_desc": e.service.service_desc,
                    "division_name": d.division_name,
                    "work_area_name": "—",
                    "remark_date": item.remark_date,
                    "remarks": item.remarks,
                    "created_by": str(item.created_by),
                    "created_on": item.created_on,
                    "_sk": (
                        e.client.display_name,
                        e.fiscal_year.fy_no,
                        e.service.service_desc,
                        item.remark_date or timezone.localdate(),
                        1,
                        d.division_name,
                        "",
                        item.pk,
                    ),
                }
            )

    if include_level("work_area"):
        for item in (
            EngagementWorkAreaStatusRemark.objects.filter(
                work_area__engagement_id__in=engagement_ids
            )
            .select_related(
                "work_area__engagement__client",
                "work_area__engagement__fiscal_year",
                "work_area__engagement__service",
                "created_by",
            )
            .order_by("id")
        ):
            wa = item.work_area
            e = wa.engagement
            rows.append(
                {
                    "scope": "Eng. work area",
                    "client_name": e.client.display_name,
                    "fy_no": e.fiscal_year.fy_no,
                    "service_desc": e.service.service_desc,
                    "division_name": "—",
                    "work_area_name": wa.work_area_name,
                    "remark_date": item.remark_date,
                    "remarks": item.remarks,
                    "created_by": str(item.created_by),
                    "created_on": item.created_on,
                    "_sk": (
                        e.client.display_name,
                        e.fiscal_year.fy_no,
                        e.service.service_desc,
                        item.remark_date or timezone.localdate(),
                        2,
                        "",
                        wa.work_area_name,
                        item.pk,
                    ),
                }
            )

        for item in (
            DivisionWorkAreaStatusRemark.objects.filter(
                work_area__division__engagement_id__in=engagement_ids
            )
            .select_related(
                "work_area__division__engagement__client",
                "work_area__division__engagement__fiscal_year",
                "work_area__division__engagement__service",
                "created_by",
            )
            .order_by("id")
        ):
            wa = item.work_area
            d = wa.division
            e = d.engagement
            rows.append(
                {
                    "scope": "Div. work area",
                    "client_name": e.client.display_name,
                    "fy_no": e.fiscal_year.fy_no,
                    "service_desc": e.service.service_desc,
                    "division_name": d.division_name,
                    "work_area_name": wa.work_area_name,
                    "remark_date": item.remark_date,
                    "remarks": item.remarks,
                    "created_by": str(item.created_by),
                    "created_on": item.created_on,
                    "_sk": (
                        e.client.display_name,
                        e.fiscal_year.fy_no,
                        e.service.service_desc,
                        item.remark_date or timezone.localdate(),
                        3,
                        d.division_name,
                        wa.work_area_name,
                        item.pk,
                    ),
                }
            )

    rows.sort(key=lambda r: r["_sk"], reverse=True)
    for row in rows:
        del row["_sk"]
    return rows


@login_required
def status_remarks_report(request):
    # Keep backward compatibility for old links/menu items:
    # status remarks are now part of the unified Work Area Notes report.
    return redirect(f"{reverse('work_area_notes_report')}?type=remark")


def _audit_query_report_rows(
    user,
    expected_filter="all",
    status_filter="all",
    type_filter="all",
    engagement_ids=None,
):
    expected_filter = (expected_filter or "all").strip().lower()
    if expected_filter not in _AUDIT_QUERY_EXPECTED_FILTERS:
        expected_filter = "all"
    status_filter = (status_filter or "all").strip().lower()
    if status_filter not in _AUDIT_QUERY_STATUS_FILTERS:
        status_filter = "all"
    type_filter = (type_filter or "all").strip().lower()
    if type_filter not in _AUDIT_QUERY_TYPE_FILTERS:
        type_filter = "all"
    if type_filter == "status":
        type_filter = AuditQuery.ENTRY_TYPE_REMARK

    if engagement_ids is None:
        engagement_ids = list(
            _engagement_queryset_for_user(user).values_list("pk", flat=True)
        )
    if not engagement_ids:
        return []

    qs = (
        AuditQuery.objects.filter(
        Q(engagement_work_area__engagement_id__in=engagement_ids)
        | Q(division_work_area__division__engagement_id__in=engagement_ids)
        )
        .select_related(
            "engagement_work_area__engagement__client",
            "engagement_work_area__engagement__fiscal_year",
            "engagement_work_area__engagement__service",
            "division_work_area__division__engagement__client",
            "division_work_area__division__engagement__fiscal_year",
            "division_work_area__division__engagement__service",
        )
        .annotate(response_count=Count("responses"))
    )
    if expected_filter != "all":
        qs = qs.filter(response_expected_from=expected_filter)
    if status_filter != "all":
        qs = qs.filter(status=status_filter)
    if type_filter != "all":
        qs = qs.filter(entry_type=type_filter)

    drafted_query_ids = set(
        AuditQueryMailDraftLog.objects.filter(audit_query_id__in=qs.values("id")).values_list(
            "audit_query_id", flat=True
        )
    )

    rows = []
    for q in qs.order_by("-query_date", "-id"):
        mail_ctx = _audit_query_mail_context(q)
        e = mail_ctx["engagement"]
        division_name = mail_ctx["division_name"]
        work_area_name = mail_ctx["work_area_name"]
        query_url = mail_ctx["query_url"]
        can_draft = bool(mail_ctx["recipients_to"])
        drafted_before = q.pk in drafted_query_ids
        draft_action_url = reverse("audit_query_open_draft", kwargs={"query_pk": q.pk})
        draft_action_url_repeat = f"{draft_action_url}?repeat=1"
        rows.append(
            {
                "client_name": e.client.display_name,
                "fy_no": e.fiscal_year.fy_no,
                "service_desc": e.service.service_desc,
                "division_name": division_name,
                "work_area_name": work_area_name,
                "query_date": q.query_date,
                "entry_type": q.get_entry_type_display(),
                "subject": q.subject,
                "details": q.query_text,
                "response_count": q.response_count,
                "amount": q.amount,
                "amount_unit": q.get_amount_unit_display(),
                "expected_from": q.get_response_expected_from_display(),
                "status": (
                    q.get_status_display()
                    if q.entry_type == AuditQuery.ENTRY_TYPE_QUERY
                    else "—"
                ),
                "working_paper_no": q.working_paper_no or "—",
                "query_url": query_url,
                "has_draft_recipients": can_draft,
                "drafted_before": drafted_before,
                "draft_action_url": draft_action_url,
                "draft_action_url_repeat": draft_action_url_repeat,
                "context_line": (
                    f"{e.client.display_name} · {e.fiscal_year.fy_no} · {e.service.service_desc} · "
                    f"{division_name if division_name != '—' else 'No division'}"
                ),
            }
        )
    return rows


@login_required
def work_area_notes_report(request):
    raw_expected = (request.GET.get("expected") or "all").strip().lower()
    if raw_expected not in _AUDIT_QUERY_EXPECTED_FILTERS:
        raw_expected = "all"
    raw_status = (request.GET.get("status") or "all").strip().lower()
    if raw_status not in _AUDIT_QUERY_STATUS_FILTERS:
        raw_status = "all"
    raw_type = (request.GET.get("type") or "all").strip().lower()
    if raw_type == "status":
        raw_type = AuditQuery.ENTRY_TYPE_REMARK
    if raw_type not in _AUDIT_QUERY_TYPE_FILTERS:
        raw_type = "all"

    rows = _audit_query_report_rows(
        request.user,
        expected_filter=raw_expected,
        status_filter=raw_status,
        type_filter=raw_type,
        engagement_ids=engagement_ids_for_lists(request.user, request),
    )
    return render(
        request,
        "engagements/audit_queries_report.html",
        {
            "rows": rows,
            "query_expected_filter": raw_expected,
            "query_status_filter": raw_status,
            "query_type_filter": raw_type,
        },
    )


@login_required
def audit_queries_report(request):
    # Backward-compatible endpoint name for old URLs.
    return work_area_notes_report(request)


@login_required
def audit_query_open_draft(request, query_pk: int):
    query = get_object_or_404(
        AuditQuery.objects.select_related(
            "engagement_work_area__engagement__client",
            "engagement_work_area__engagement__fiscal_year",
            "engagement_work_area__engagement__service",
            "division_work_area__division__engagement__client",
            "division_work_area__division__engagement__fiscal_year",
            "division_work_area__division__engagement__service",
        ),
        pk=query_pk,
    )

    if query.engagement_work_area_id:
        engagement_id = query.engagement_work_area.engagement_id
    elif query.division_work_area_id:
        engagement_id = query.division_work_area.division.engagement_id
    else:
        raise Http404("Note is not linked to a work area.")
    if not _engagement_queryset_for_user(request.user).filter(pk=engagement_id).exists():
        raise PermissionDenied("You do not have access to this note.")

    repeat = (request.GET.get("repeat") or "").strip().lower() in {"1", "true", "yes"}
    already_drafted = AuditQueryMailDraftLog.objects.filter(audit_query=query).exists()
    if already_drafted and not repeat:
        messages.info(
            request,
            "Draft already created for this note. Use Repeat draft if you want another copy.",
        )
        return redirect("work_area_notes_report")

    mail_ctx = _audit_query_mail_context(query)
    recipients_to = mail_ctx["recipients_to"]
    recipients_cc = mail_ctx["recipients_cc"]
    if not recipients_to:
        messages.warning(request, "No recipient email IDs available for this note.")
        return redirect("work_area_notes_report")

    mailto_url = _build_note_mailto_url(
        recipients_to=recipients_to,
        recipients_cc=recipients_cc,
        subject=mail_ctx["subject"],
        body=mail_ctx["body"],
    )
    AuditQueryMailDraftLog.objects.create(
        audit_query=query,
        recipient_to=", ".join(recipients_to),
        recipient_cc=", ".join(recipients_cc),
        subject=mail_ctx["subject"][:255],
        drafted_by=request.user,
    )
    return HttpResponse(
        (
            "<!doctype html><html><body>"
            "<p>Opening draft mail...</p>"
            f"<p><a href=\"{mailto_url}\">If not opened, click here</a></p>"
            f"<script>window.location.href = {json.dumps(mailto_url)};</script>"
            "</body></html>"
        )
    )
