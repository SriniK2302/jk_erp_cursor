from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Count, Exists, F, Max, Min, OuterRef, Prefetch, Q
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.dateparse import parse_date
from django.utils.text import get_valid_filename
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import io
import json
import logging
import re
from urllib.parse import urlencode, quote

from sales.client_classifications.models import ClientClassification
from hr.teams.models import TeamMember

from engagements.documentations.word_template import word_template_content_type
from engagements.documentations.representation_matrix import (
    is_mr02_documentation,
    mr02_point_rows,
    parse_representation_matrix_post,
    REPRESENTATION_POINT_STATUS_CHOICES,
)
from engagements.documentations.word_template_fill import (
    fill_docx_template,
    filled_engagement_documentation_docx_filename,
    list_unresolved_tokens_in_document_xml,
    merge_context_for_engagement,
)

from . import team_mail
from .forms import (
    DivisionWorkAreaTeamAssignmentForm,
    _engagement_schedule_bounds,
    EngagementDivisionForm,
    EngagementDivisionDocumentationMapForm,
    EngagementDivisionTeamAssignmentForm,
    EngagementDocumentationMapForm,
    EngagementForm,
    EngagementWorkAreaTeamAssignmentForm,
    DivisionWorkAreaForm,
    DivisionWorkAreaPeriodForm,
    EngagementScheduleForm,
    EngagementTeamAssignmentForm,
    EngagementWorkAreaForm,
    EngagementWorkAreaPeriodForm,
    filter_engagement_documentation_by_client_classification,
)
from .models import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_SCHEDULED,
    Engagement,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    EngagementDocumentationMapAttachment,
    EngagementTeamAssignment,
    DivisionWorkArea,
    DivisionWorkAreaPeriod,
    DivisionWorkAreaDocument,
    AuditQuery,
    AuditQueryAttachment,
    AuditQueryMailDraftLog,
    AuditQueryResponse,
    DivisionWorkAreaStatusRemark,
    DivisionWorkAreaTeamAssignment,
    EngagementDivisionStatusRemark,
    EngagementSchedule,
    EngagementStatusRemark,
    EngagementWorkArea,
    EngagementWorkAreaStatusRemark,
    EngagementWorkAreaTeamAssignment,
    EngagementWorkAreaDocument,
    EngagementWorkAreaPeriod,
    ServiceEngagementChecklistWorkArea,
)
from .closure import assert_division_open_for_management, assert_engagement_open_for_management
from .session_context import (
    engagement_ids_for_lists,
    engagement_select_label,
    clear_session_engagement,
    filter_by_engagement_id,
    filter_engagement_queryset,
    set_session_engagement,
)
from .work_area_notes_batch import (
    batch_save_wants_json,
    checklist_items_queryset,
    add_all_checklist_lines_to_notes_log,
    json_batch_save_response,
    save_work_area_notes_batch,
    save_work_area_notes_batch_single_row,
    work_area_has_checklist_template,
    work_area_notes_list_page_context,
    work_area_notes_page_context,
)
from .timesheets.models import TimeSession
from .timesheets.views import (
    my_time_log,
    timer_recent_tasks,
    timer_start_division,
    timer_start_division_work_area,
    timer_start_engagement,
    timer_start_engagement_work_area,
    timer_stop,
)

# NOTE FOR MAINTAINERS:
# Write-heavy flows that touch multiple rows/tables are wrapped in
# transaction.atomic() in this module. Keep that pattern for:
# - work-area create/edit + resequencing
# - copy/prefill bulk operations
# - schedule save + optional engagement schedule backfill
# - multi-file upload actions


@login_required
def manage_engagements(request):
    return render(
        request,
        "engagements/manage_engagements.html",
        {"can_manage_structure": _can_manage_structure(request.user)},
    )


@login_required
def certification_fees(request):
    from engagements.session_context import get_session_engagement
    from sales.udins.certification_period_fee import bulk_apply_certification_period_fees_to_udins
    from sales.udins.models import CertificationPeriodFee

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "delete":
            row = get_object_or_404(CertificationPeriodFee, pk=request.POST.get("pk"))
            row.delete()
            messages.success(request, "Certification fee period deleted.")
            return redirect("certification_fees")
        if action == "apply_to_udins":
            updated, skipped = bulk_apply_certification_period_fees_to_udins(only_blank=True)
            messages.success(
                request,
                f"Applied certification fees to {updated} UDIN row(s) across all clients. "
                f"Skipped {skipped} row(s) (not Certification, Inv TV already set, or no matching fee).",
            )
            return redirect("certification_fees")
        return redirect("certification_fees")

    rows = CertificationPeriodFee.objects.select_related("client").all()
    session = get_session_engagement(request)
    if session is not None:
        rows = rows.filter(client_id=session.client_id)
    return render(
        request,
        "engagements/certification_fees.html",
        {"rows": rows},
    )


def _certification_fee_form_view(request, instance=None):
    from engagements.session_context import get_session_engagement
    from sales.udins.forms import CertificationPeriodFeeForm

    if request.method == "POST":
        form = CertificationPeriodFeeForm(request.POST, instance=instance)
        if form.is_valid():
            row = form.save()
            from sales.udins.certification_period_fee import bulk_apply_certification_period_fees_to_udins

            updated, skipped = bulk_apply_certification_period_fees_to_udins(
                only_blank=True,
                client_id=row.client_id,
            )
            messages.success(
                request,
                f"Certification fee period saved. Set Inv TV amt on {updated} matching UDIN row(s) "
                f"for {row.client.client_short_name}. Skipped {skipped} row(s).",
            )
            return redirect("certification_fees")
    else:
        initial = {}
        if instance is None:
            session = get_session_engagement(request)
            if session is not None:
                initial["client"] = session.client_id
                if session.fiscal_year_id:
                    initial["from_date"] = session.fiscal_year.start_date
                    initial["to_date"] = session.fiscal_year.end_date
        form = CertificationPeriodFeeForm(instance=instance, initial=initial)
    return render(
        request,
        "engagements/certification_fee_form.html",
        {"form": form, "row": instance},
    )


@login_required
def certification_fee_create(request):
    return _certification_fee_form_view(request)


@login_required
def certification_fee_edit(request, pk):
    from sales.udins.models import CertificationPeriodFee

    row = get_object_or_404(CertificationPeriodFee, pk=pk)
    return _certification_fee_form_view(request, instance=row)


def _session_engagement_next_url(request):
    nxt = (request.POST.get("next") or "").strip()
    fallback = reverse("manage_engagements")
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return nxt
    return fallback


@login_required
@require_POST
def session_engagement_set(request):
    next_url = _session_engagement_next_url(request)
    raw_id = (request.POST.get("engagement_id") or "").strip()
    if not raw_id:
        clear_session_engagement(request)
        messages.info(request, "Working engagement cleared.")
        return redirect(next_url)
    if not raw_id.isdigit():
        messages.error(request, "Invalid engagement selection.")
        return redirect(next_url)
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=int(raw_id),
    )
    set_session_engagement(request, engagement)
    messages.success(
        request,
        f"Working engagement set to {engagement_select_label(engagement)}.",
    )
    return redirect(next_url)


@login_required
@require_POST
def session_engagement_clear(request):
    clear_session_engagement(request)
    messages.info(request, "Working engagement cleared.")
    return redirect(_session_engagement_next_url(request))


_TEAM_ASSIGNMENT_REPORT_STATUS_FILTERS = frozenset({"current", "completed"})
_STATUS_REMARK_REPORT_LEVEL_FILTERS = frozenset(
    {"all", "engagement", "division", "work_area"}
)
_AUDIT_QUERY_EXPECTED_FILTERS = frozenset({"all", "internal", "client"})
_AUDIT_QUERY_STATUS_FILTERS = frozenset({"all", "open", "closed"})
_AUDIT_QUERY_TYPE_FILTERS = frozenset({"all", "query", "remark"})


def _split_mail_ids(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[,\n;]+", text) if p.strip()]
    return list(dict.fromkeys(parts))


def _work_area_team_recipient_ids(*, engagement_work_area=None, division_work_area=None) -> list[str]:
    recipients: list[str] = []
    if engagement_work_area is not None:
        assignments = EngagementWorkAreaTeamAssignment.objects.filter(
            work_area=engagement_work_area
        ).select_related("team_member")
    elif division_work_area is not None:
        assignments = DivisionWorkAreaTeamAssignment.objects.filter(
            work_area=division_work_area
        ).select_related("team_member")
    else:
        return recipients
    for assignment in assignments:
        email = (assignment.team_member.work_email or "").strip()
        if email:
            recipients.append(email)
    return list(dict.fromkeys(recipients))


def _client_recipients_for_note(*, engagement, division=None) -> list[str]:
    recipients: list[str] = []
    client = engagement.client
    if (client.mail_id or "").strip():
        recipients.append((client.mail_id or "").strip())
    recipients.extend(_split_mail_ids(client.additional_mail_ids or ""))
    if (engagement.engagement_mail_id or "").strip():
        recipients.append((engagement.engagement_mail_id or "").strip())
    recipients.extend(_split_mail_ids(engagement.additional_mail_ids or ""))
    if division is not None:
        recipients.extend(_split_mail_ids(division.division_mail_ids or ""))
    return list(dict.fromkeys(recipients))


def _build_note_mailto_url(
    *,
    recipients_to: list[str],
    recipients_cc: list[str],
    subject: str,
    body: str,
) -> str:
    to_part = ",".join(recipients_to)
    query = urlencode({"cc": ",".join(recipients_cc), "subject": subject, "body": body})
    return f"mailto:{quote(to_part, safe='@,')}" + (f"?{query}" if query else "")


def _audit_query_mail_context(q: AuditQuery) -> dict:
    if q.engagement_work_area_id:
        wa = q.engagement_work_area
        e = wa.engagement
        division_name = "—"
        work_area_name = wa.work_area_name
        team_recipients = _work_area_team_recipient_ids(engagement_work_area=wa)
        client_recipients = _client_recipients_for_note(engagement=e)
    else:
        wa = q.division_work_area
        d = wa.division
        e = d.engagement
        division_name = d.division_name
        work_area_name = wa.work_area_name
        team_recipients = _work_area_team_recipient_ids(division_work_area=wa)
        client_recipients = _client_recipients_for_note(engagement=e, division=d)

    if q.response_expected_from == AuditQuery.RESPONDER_CLIENT:
        recipients_to = client_recipients
    else:
        recipients_to = team_recipients
    recipients_cc: list[str] = []
    note_label = q.get_entry_type_display()
    query_url = (
        reverse(
            "engagement_work_area_queries",
            kwargs={"engagement_pk": e.pk, "work_area_pk": wa.pk},
        )
        if q.engagement_work_area_id
        else reverse(
            "engagement_division_work_area_queries",
            kwargs={"division_pk": wa.division.pk, "work_area_pk": wa.pk},
        )
    )
    draft_subject = (
        f"{note_label}: {e.client.display_name} ({e.fiscal_year.fy_no}) - "
        f"{e.service.service_desc} - {work_area_name}"
    )
    draft_body = (
        f"Dear Team,\n\n"
        f"Please review the following {note_label.lower()} item.\n\n"
        f"Client: {e.client.display_name}\n"
        f"Fiscal year: {e.fiscal_year.fy_no}\n"
        f"Service: {e.service.service_desc}\n"
        f"Division: {division_name if division_name != '—' else 'No division'}\n"
        f"Work area: {work_area_name}\n"
        f"Date: {q.query_date.isoformat() if q.query_date else ''}\n"
        f"Type: {note_label}\n"
        f"Expected from: {q.get_response_expected_from_display()}\n"
        f"Status: {q.get_status_display()}\n"
        f"Subject: {q.subject}\n"
        f"Details:\n{q.query_text}\n\n"
        f"Open in JK ERP: {query_url}\n"
    )
    return {
        "engagement": e,
        "division_name": division_name,
        "work_area_name": work_area_name,
        "recipients_to": recipients_to,
        "recipients_cc": recipients_cc,
        "subject": draft_subject,
        "body": draft_body,
        "query_url": query_url,
    }


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


@login_required
def bulk_engagement_team_assignments(request):
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")

    engagement_items = filter_engagement_queryset(
        _engagement_queryset_for_user(request.user)
        .exclude(status=STATUS_COMPLETED)
        .select_related("client", "fiscal_year", "service")
        .order_by("client__client_name", "fiscal_year__fy_no", "service__service_desc"),
        request,
    )
    team_members = TeamMember.objects.order_by("first_name", "last_name", "code")

    if request.method == "POST":
        member_id = (request.POST.get("team_member_id") or "").strip()
        selected_ids = request.POST.getlist("engagement_ids")
        if not member_id.isdigit():
            messages.error(request, "Select a team member.")
            return render(
                request,
                "engagements/bulk_engagement_team_assignments.html",
                {
                    "engagements": engagement_items,
                    "team_members": team_members,
                    "selected_member_id": member_id,
                    "selected_ids": {str(v) for v in selected_ids},
                },
            )

        team_member = TeamMember.objects.filter(pk=int(member_id)).first()
        if team_member is None:
            messages.error(request, "Selected team member is invalid.")
            return redirect("bulk_engagement_team_assignments")

        ids = [int(v) for v in selected_ids if str(v).isdigit()]
        if not ids:
            messages.error(request, "Select at least one engagement.")
            return render(
                request,
                "engagements/bulk_engagement_team_assignments.html",
                {
                    "engagements": engagement_items,
                    "team_members": team_members,
                    "selected_member_id": str(team_member.pk),
                    "selected_ids": set(),
                },
            )

        created = 0
        skipped_no_schedule = 0
        skipped_overlap = 0
        skipped_missing = 0
        selected_qs = engagement_items.filter(pk__in=ids)
        selected_by_id = {e.pk: e for e in selected_qs}

        for engagement_id in ids:
            engagement = selected_by_id.get(engagement_id)
            if engagement is None:
                skipped_missing += 1
                continue
            bounds = engagement.schedules.aggregate(
                earliest=Min("planned_start"),
                latest=Max("planned_finish"),
            )
            planned_start = bounds.get("earliest")
            planned_finish = bounds.get("latest")
            if not planned_start or not planned_finish:
                skipped_no_schedule += 1
                continue

            overlaps = EngagementTeamAssignment.objects.filter(
                engagement=engagement,
                team_member=team_member,
                planned_start__lte=planned_finish,
                planned_finish__gte=planned_start,
            ).exists()
            if overlaps:
                skipped_overlap += 1
                continue

            EngagementTeamAssignment.objects.create(
                engagement=engagement,
                team_member=team_member,
                planned_start=planned_start,
                planned_finish=planned_finish,
                created_by=request.user,
            )
            created += 1

        if created:
            messages.success(
                request,
                f"Added {team_member} to {created} engagement(s).",
            )
        if skipped_no_schedule:
            messages.warning(
                request,
                f"Skipped {skipped_no_schedule} engagement(s) without planned schedule dates.",
            )
        if skipped_overlap:
            messages.info(
                request,
                f"Skipped {skipped_overlap} engagement(s) due to existing overlapping assignment for this member.",
            )
        if skipped_missing:
            messages.warning(
                request,
                f"Skipped {skipped_missing} selection(s) that are unavailable.",
            )
        return redirect("bulk_engagement_team_assignments")

    return render(
        request,
        "engagements/bulk_engagement_team_assignments.html",
        {
            "engagements": engagement_items,
            "team_members": team_members,
            "selected_member_id": "",
            "selected_ids": set(),
        },
    )


@login_required
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


_ENGAGEMENT_LIST_STATUS_FILTERS = frozenset(
    {"active", "all", "pending", "scheduled", "in_progress", "completed"}
)
_DIVISION_TEAM_LIST_FILTERS = frozenset({"all", "unassigned"})
_DIVISION_STATUS_LIST_FILTERS = frozenset({"active", "all"})
_WORK_AREA_STATUS_FILTERS = frozenset({"active", "all"})
_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY = "engagement_divisions_team_filter"
_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY = "engagement_divisions_status_filter"
ENGAGEMENTS_MODULE_GROUP = "module_engagements"


def _has_engagements_module_access(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name=ENGAGEMENTS_MODULE_GROUP).exists()


def _can_manage_structure(user):
    return user.is_superuser


def _engagement_queryset_for_user(user):
    qs = Engagement.objects.all()
    if user.is_superuser:
        return qs
    if not _has_engagements_module_access(user):
        return qs.none()
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(divisions__team_assignments__team_member_id__in=team_member)
        | Q(work_areas__team_assignments__team_member_id__in=team_member)
        | Q(divisions__work_areas__team_assignments__team_member_id__in=team_member)
    ).distinct()


def _engagement_division_queryset_for_user(user):
    qs = EngagementDivision.objects.all()
    if user.is_superuser:
        return qs
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(engagement__team_assignments__team_member_id__in=team_member)
        | Q(work_areas__team_assignments__team_member_id__in=team_member)
    ).distinct()


def _engagement_work_area_queryset_for_user(user):
    qs = EngagementWorkArea.objects.all()
    if user.is_superuser:
        return qs
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(engagement__team_assignments__team_member_id__in=team_member)
    ).distinct()


def _division_work_area_queryset_for_user(user):
    qs = DivisionWorkArea.objects.all()
    if user.is_superuser:
        return qs
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(division__team_assignments__team_member_id__in=team_member)
        | Q(division__engagement__team_assignments__team_member_id__in=team_member)
    ).distinct()


def _active_time_session_for_user(user):
    if not user.is_authenticated:
        return None
    try:
        return (
            TimeSession.objects.filter(started_by=user, ended_at__isnull=True)
            .select_related(
                "engagement__client",
                "engagement__fiscal_year",
                "engagement__service",
                "division",
                "engagement_work_area",
                "division_work_area",
            )
            .order_by("-started_at", "-id")
            .first()
        )
    except (OperationalError, ProgrammingError):
        return None


def _timer_scope_dict(session):
    if session is None:
        return {}
    return {
        "engagement_id": session.engagement_id or 0,
        "division_id": session.division_id or 0,
        "engagement_work_area_id": session.engagement_work_area_id or 0,
        "division_work_area_id": session.division_work_area_id or 0,
    }


@login_required
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


def _engagement_form_view(request, instance=None):
    if instance is not None:
        assert_engagement_open_for_management(request.user, instance)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementForm(request.POST, instance=instance)
        if form.is_valid():
            engagement = form.save(commit=False)
            if instance is None:
                engagement.created_by = request.user
            engagement.save()
            label = (
                f"{engagement.client.display_name} · "
                f"{engagement.fiscal_year.fy_no} · "
                f"{engagement.service.service_desc}"
            )
            if instance is None:
                messages.success(request, f"Engagement saved: {label}")
            else:
                messages.success(request, f"Engagement updated: {label}")
            return redirect("engagements")
    else:
        form = EngagementForm(instance=instance)

    team_assignments = []
    if instance is not None:
        team_assignments = list(
            instance.team_assignments.select_related("team_member").all()
        )

    return render(
        request,
        "engagements/engagement_form.html",
        {
            "form": form,
            "engagement": instance,
            "team_assignments": team_assignments,
        },
    )


@login_required
def engagement_create(request):
    return _engagement_form_view(request)


@login_required
def engagement_edit(request, pk):
    engagement = get_object_or_404(_engagement_queryset_for_user(request.user), pk=pk)
    return _engagement_form_view(request, instance=engagement)


@login_required
def engagement_schedules(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            schedule = get_object_or_404(
                EngagementSchedule,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            if (
                not request.user.is_superuser
                and schedule.actual_finish is not None
                and not engagement.schedules.exclude(pk=schedule.pk).filter(
                    actual_finish__isnull=False
                ).exists()
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed engagement.",
                )
                return redirect("engagement_schedules", engagement_pk=engagement.pk)
            schedule.delete()
            return redirect("engagement_schedules", engagement_pk=engagement.pk)
        return redirect("engagement_schedules", engagement_pk=engagement.pk)

    schedules = engagement.schedules.all()
    team_assignments = engagement.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_schedules.html",
        {
            "engagement": engagement,
            "schedules": schedules,
            "team_assignments": team_assignments,
        },
    )


def _engagement_schedule_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = EngagementScheduleForm(request.POST, instance=instance)
        if form.is_valid():
            schedule = form.save(commit=False)
            if not _can_manage_structure(request.user) and instance is not None:
                schedule.planned_start = original_planned_start
                schedule.planned_finish = original_planned_finish
            if (
                instance is not None
                and not request.user.is_superuser
                and had_actual_finish
                and schedule.actual_finish is None
                and not engagement.schedules.exclude(pk=instance.pk).filter(
                    actual_finish__isnull=False
                ).exists()
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed engagement.",
                )
                return redirect("engagement_schedules", engagement_pk=engagement.pk)
            if instance is None:
                schedule.engagement = engagement
                schedule.created_by = request.user
            schedule.save()
            return redirect("engagement_schedules", engagement_pk=engagement.pk)
    else:
        form = EngagementScheduleForm(instance=instance)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    return render(
        request,
        "engagements/engagement_schedule_form.html",
        {
            "form": form,
            "engagement": engagement,
            "schedule": instance,
        },
    )


@login_required
def engagement_schedule_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    return _engagement_schedule_form_view(request, engagement=engagement)


@login_required
def engagement_schedule_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    schedule = get_object_or_404(EngagementSchedule, pk=pk, engagement=engagement)
    return _engagement_schedule_form_view(
        request,
        engagement=engagement,
        instance=schedule,
    )


@login_required
def engagement_team_assignments(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            assignment = get_object_or_404(
                EngagementTeamAssignment,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            assignment.delete()
            return redirect("engagement_team_assignments", engagement_pk=engagement.pk)
        if action == "send_assignment_mail":
            assignment = get_object_or_404(
                EngagementTeamAssignment,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            team_mail.manual_notify_engagement_team_assignment(request, assignment)
            return redirect("engagement_team_assignments", engagement_pk=engagement.pk)
        return redirect("engagement_team_assignments", engagement_pk=engagement.pk)

    team_assignments = engagement.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_team_assignments.html",
        {
            "engagement": engagement,
            "team_assignments": team_assignments,
            "today": timezone.localdate(),
        },
    )


def _engagement_team_assignment_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementTeamAssignmentForm(
            request.POST,
            instance=instance,
            engagement=engagement,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.engagement = engagement
                assignment.created_by = request.user
            assignment.save()
            team_mail.maybe_auto_notify_engagement_team_assignment(request, assignment)
            return redirect("engagement_team_assignments", engagement_pk=engagement.pk)
    else:
        form = EngagementTeamAssignmentForm(instance=instance, engagement=engagement)

    return render(
        request,
        "engagements/engagement_team_assignment_form.html",
        {
            "form": form,
            "engagement": engagement,
            "assignment": instance,
        },
    )


@login_required
def engagement_team_assignment_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    return _engagement_team_assignment_form_view(request, engagement=engagement)


@login_required
def engagement_team_assignment_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    assignment = get_object_or_404(
        EngagementTeamAssignment,
        pk=pk,
        engagement=engagement,
    )
    return _engagement_team_assignment_form_view(
        request,
        engagement=engagement,
        instance=assignment,
    )


def _work_area_display_name_from_service_template(template):
    text = (template.name or "").strip()
    return text[:150]


def _service_checklist_templates_for_service(service_id: int):
    return (
        ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id)
        .annotate(checklist_line_count=Count("items"))
        .order_by("sort_order", "id")
    )


def _service_work_area_pick_rows(wa_qs, templates):
    existing_fk = set(
        wa_qs.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in wa_qs.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    rows = []
    for t in templates:
        name_cf = (t.name or "").strip().casefold()
        already = t.pk in existing_fk or (name_cf and name_cf in existing_names_cf)
        line_count = getattr(t, "checklist_line_count", None)
        if line_count is None:
            line_count = t.items.count()
        rows.append(
            {
                "template": t,
                "already_added": already,
                "checklist_line_count": line_count,
                "can_map": line_count > 0,
            }
        )
    return rows


def _engagement_service_work_area_pick_rows(engagement, templates):
    return _service_work_area_pick_rows(
        EngagementWorkArea.objects.filter(engagement=engagement),
        templates,
    )


def _division_service_work_area_pick_rows(division, templates):
    return _service_work_area_pick_rows(
        DivisionWorkArea.objects.filter(division=division),
        templates,
    )


def _add_engagement_work_areas_from_service_templates(request, engagement, template_ids):
    if not template_ids:
        return 0
    templates = list(
        ServiceEngagementChecklistWorkArea.objects.filter(
            pk__in=template_ids,
            service_id=engagement.service_id,
        ).annotate(checklist_line_count=Count("items"))
    )
    if not templates:
        return 0
    existing_q = EngagementWorkArea.objects.filter(engagement=engagement)
    existing_fk = set(
        existing_q.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in existing_q.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    created = 0
    with transaction.atomic():
        for tpl in templates:
            if getattr(tpl, "checklist_line_count", 0) < 1:
                continue
            if tpl.pk in existing_fk:
                continue
            wa_name = _work_area_display_name_from_service_template(tpl)
            if not wa_name:
                continue
            name_cf = wa_name.casefold()
            if name_cf in existing_names_cf:
                continue
            EngagementWorkArea.objects.create(
                engagement=engagement,
                work_area_name=wa_name,
                sort_order=9999,
                created_by=request.user,
                service_checklist_work_area=tpl,
            )
            existing_fk.add(tpl.pk)
            existing_names_cf.add(name_cf)
            created += 1
        if created:
            ordered_ids = list(
                EngagementWorkArea.objects.filter(engagement=engagement)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                EngagementWorkArea.objects.filter(pk=pk).update(sort_order=idx)
    return created


def _add_division_work_areas_from_service_templates(request, division, template_ids):
    if not template_ids:
        return 0
    service_id = division.engagement.service_id
    templates = list(
        ServiceEngagementChecklistWorkArea.objects.filter(
            pk__in=template_ids,
            service_id=service_id,
        ).annotate(checklist_line_count=Count("items"))
    )
    if not templates:
        return 0
    existing_q = DivisionWorkArea.objects.filter(division=division)
    existing_fk = set(
        existing_q.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in existing_q.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    created = 0
    with transaction.atomic():
        for tpl in templates:
            if getattr(tpl, "checklist_line_count", 0) < 1:
                continue
            if tpl.pk in existing_fk:
                continue
            wa_name = _work_area_display_name_from_service_template(tpl)
            if not wa_name:
                continue
            name_cf = wa_name.casefold()
            if name_cf in existing_names_cf:
                continue
            DivisionWorkArea.objects.create(
                division=division,
                work_area_name=wa_name,
                sort_order=9999,
                created_by=request.user,
                service_checklist_work_area=tpl,
            )
            existing_fk.add(tpl.pk)
            existing_names_cf.add(name_cf)
            created += 1
        if created:
            ordered_ids = list(
                DivisionWorkArea.objects.filter(division=division)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)
    return created


def _mappable_template_ids_not_on_scope(pick_rows) -> list[int]:
    return [
        row["template"].pk
        for row in pick_rows
        if row.get("can_map") and not row.get("already_added")
    ]


def _bulk_add_all_standard_work_areas(
    request,
    *,
    engagement=None,
    division=None,
    pick_rows,
) -> dict[str, int]:
    template_ids = _mappable_template_ids_not_on_scope(pick_rows)
    work_areas_added = 0
    checklist_lines_added = 0

    with transaction.atomic():
        if engagement is not None:
            work_areas_added = _add_engagement_work_areas_from_service_templates(
                request, engagement, template_ids
            )
            work_area_qs = EngagementWorkArea.objects.filter(
                engagement=engagement
            )
            engagement_work_area = True
        else:
            work_areas_added = _add_division_work_areas_from_service_templates(
                request, division, template_ids
            )
            work_area_qs = DivisionWorkArea.objects.filter(division=division)
            engagement_work_area = False

        for work_area in work_area_qs:
            if not work_area_has_checklist_template(work_area):
                continue
            created, _errs = add_all_checklist_lines_to_notes_log(
                request,
                work_area,
                engagement_work_area=engagement_work_area,
            )
            checklist_lines_added += created

    return {
        "work_areas_added": work_areas_added,
        "checklist_lines_added": checklist_lines_added,
    }


def _bulk_delete_work_areas_without_queries(
    *,
    engagement=None,
    division=None,
) -> dict[str, int]:
    if engagement is not None:
        qs = EngagementWorkArea.objects.filter(engagement=engagement)
    else:
        qs = DivisionWorkArea.objects.filter(division=division)

    annotated = qs.annotate(query_count=Count("audit_queries"))
    to_delete = annotated.filter(query_count=0)
    skipped_with_queries = annotated.filter(query_count__gt=0).count()
    deleted = to_delete.count()

    with transaction.atomic():
        to_delete.delete()
        if engagement is not None:
            ordered_ids = list(
                EngagementWorkArea.objects.filter(engagement=engagement)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                EngagementWorkArea.objects.filter(pk=pk).update(sort_order=idx)
        else:
            ordered_ids = list(
                DivisionWorkArea.objects.filter(division=division)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)

    return {
        "deleted": deleted,
        "skipped_with_queries": skipped_with_queries,
    }


def _json_bulk_work_areas_response(*, ok: bool, message: str = "", stats: dict | None = None, status: int = 200):
    payload = {"ok": ok, "message": message}
    if stats:
        payload.update(stats)
    if not ok:
        return JsonResponse(payload, status=status if status != 200 else 400)
    return JsonResponse(payload, status=status)


@login_required
def engagement_work_areas(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    assert_engagement_open_for_management(request.user, engagement)

    def _work_areas_redirect():
        base = reverse("engagement_work_areas", kwargs={"engagement_pk": engagement.pk})
        if raw_status == "all":
            return redirect(f"{base}?{urlencode({'status': raw_status})}")
        return redirect(base)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_from_service_templates":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            raw_ids = []
            for raw in request.POST.getlist("service_work_area_ids"):
                try:
                    raw_ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
            raw_ids = list(dict.fromkeys(raw_ids))
            created = _add_engagement_work_areas_from_service_templates(
                request, engagement, raw_ids
            )
            if created:
                messages.success(
                    request,
                    f"Added {created} work area(s) from the service standard list.",
                )
            else:
                messages.info(
                    request,
                    "No new work areas were added (none selected, or all were already present).",
                )
            return _work_areas_redirect()
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            work_area = get_object_or_404(
                EngagementWorkArea,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            work_area.delete()
            return _work_areas_redirect()
        if action == "bulk_add_all_standard":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            service_template_list = list(
                _service_checklist_templates_for_service(engagement.service_id)
            )
            all_service_pick_rows = _engagement_service_work_area_pick_rows(
                engagement, service_template_list
            )
            stats = _bulk_add_all_standard_work_areas(
                request,
                engagement=engagement,
                pick_rows=all_service_pick_rows,
            )
            msg = (
                f"Added {stats['work_areas_added']} work area(s) and "
                f"{stats['checklist_lines_added']} checklist line(s) to the notes log."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _work_areas_redirect()
        if action == "bulk_delete_all_without_queries":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            stats = _bulk_delete_work_areas_without_queries(engagement=engagement)
            msg = (
                f"Deleted {stats['deleted']} work area(s). "
                f"Kept {stats['skipped_with_queries']} with notes/queries."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _work_areas_redirect()
        return _work_areas_redirect()

    work_areas = (
        _engagement_work_area_queryset_for_user(request.user)
        .filter(engagement=engagement)
        .annotate(
            schedule_row_count=Count("schedule_rows"),
            document_count=Count("documents"),
            assignment_count=Count("team_assignments"),
            status_remark_count=Count("status_remarks"),
        )
        .order_by("work_area_name", "sort_order", "id")
    )
    team_assignments = engagement.team_assignments.select_related("team_member").all()
    if raw_status == "active":
        work_areas = work_areas.exclude(status=STATUS_COMPLETED)
    service_template_list = list(
        _service_checklist_templates_for_service(engagement.service_id)
    )
    all_service_pick_rows = _engagement_service_work_area_pick_rows(
        engagement, service_template_list
    )
    service_work_area_pick_rows = [
        r for r in all_service_pick_rows if not r["already_added"]
    ]
    service_standard_template_count = len(service_template_list)
    return render(
        request,
        "engagements/engagement_work_areas.html",
        {
            "engagement": engagement,
            "work_areas": work_areas,
            "team_assignments": team_assignments,
            "work_area_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
            "service_work_area_pick_rows": service_work_area_pick_rows,
            "service_standard_template_count": service_standard_template_count,
        },
    )


@login_required
def engagement_work_area_notes_list(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    rows = (
        AuditQuery.objects.filter(engagement_work_area__engagement=engagement)
        .select_related("engagement_work_area")
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    ctx = work_area_notes_list_page_context(
        engagement=engagement,
        rows=rows,
    )
    return render(request, "engagements/work_area_notes_list.html", ctx)


@login_required
def engagement_all_work_area_notes(request, engagement_pk):
    """Queries/remarks across engagement-level and all division work areas."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    rows = (
        AuditQuery.objects.filter(
            Q(engagement_work_area__engagement=engagement)
            | Q(division_work_area__division__engagement=engagement)
        )
        .select_related(
            "engagement_work_area",
            "division_work_area__division",
        )
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    return render(
        request,
        "engagements/engagement_all_work_area_notes.html",
        {
            "engagement": engagement,
            "rows": rows,
        },
    )


def _resequence_scoped_work_areas(*, model, scope_filter, target_pk, requested_order):
    siblings = list(
        model.objects.filter(**scope_filter)
        .exclude(pk=target_pk)
        .order_by("sort_order", "id")
        .values_list("pk", flat=True)
    )
    total = len(siblings) + 1
    try:
        position = int(requested_order or total)
    except (TypeError, ValueError):
        position = total
    position = max(1, min(position, total))

    ordered_ids = siblings.copy()
    ordered_ids.insert(position - 1, target_pk)
    for idx, pk in enumerate(ordered_ids, start=1):
        model.objects.filter(pk=pk).update(sort_order=idx)


def _engagement_work_area_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementWorkAreaForm(
            request.POST,
            instance=instance,
            engagement=engagement,
        )
        if form.is_valid():
            with transaction.atomic():
                work_area = form.save(commit=False)
                if instance is None:
                    work_area.engagement = engagement
                    work_area.created_by = request.user
                work_area.save()
                _resequence_scoped_work_areas(
                    model=EngagementWorkArea,
                    scope_filter={"engagement": engagement},
                    target_pk=work_area.pk,
                    requested_order=form.cleaned_data.get("sort_order"),
                )
            return redirect("engagement_work_areas", engagement_pk=engagement.pk)
    else:
        form = EngagementWorkAreaForm(instance=instance, engagement=engagement)

    return render(
        request,
        "engagements/engagement_work_area_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": instance,
        },
    )


@login_required
def engagement_work_area_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    return _engagement_work_area_form_view(request, engagement=engagement)


@login_required
def engagement_work_area_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=pk,
        engagement=engagement,
    )
    return _engagement_work_area_form_view(
        request,
        engagement=engagement,
        instance=work_area,
    )


@login_required
def engagement_work_area_assignments(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            assignment = get_object_or_404(
                EngagementWorkAreaTeamAssignment,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            assignment.delete()
            return redirect(
                "engagement_work_area_assignments",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_work_area_assignments",
            engagement_pk=engagement.pk,
            work_area_pk=work_area.pk,
        )

    assignments = work_area.team_assignments.select_related("team_member")
    return render(
        request,
        "engagements/engagement_work_area_assignments.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "assignments": assignments,
        },
    )


def _engagement_work_area_assignment_form_view(request, engagement, work_area, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementWorkAreaTeamAssignmentForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.work_area = work_area
                assignment.created_by = request.user
            assignment.save()
            return redirect(
                "engagement_work_area_assignments",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = EngagementWorkAreaTeamAssignmentForm(
            instance=instance, work_area=work_area
        )
    return render(
        request,
        "engagements/engagement_work_area_assignment_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": work_area,
            "assignment": instance,
        },
    )


@login_required
def engagement_work_area_assignment_create(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    return _engagement_work_area_assignment_form_view(
        request, engagement=engagement, work_area=work_area
    )


@login_required
def engagement_work_area_assignment_edit(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    assignment = get_object_or_404(
        EngagementWorkAreaTeamAssignment,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_work_area_assignment_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
        instance=assignment,
    )


@login_required
def engagement_work_area_schedule(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            schedule_row = get_object_or_404(
                EngagementWorkAreaPeriod,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            if (
                not request.user.is_superuser
                and schedule_row.actual_finish is not None
                and not work_area.schedule_rows.exclude(pk=schedule_row.pk).filter(
                    actual_finish__isnull=False
                ).exists()
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed work area.",
                )
                return redirect(
                    "engagement_work_area_schedule",
                    engagement_pk=engagement.pk,
                    work_area_pk=work_area.pk,
                )
            schedule_row.delete()
            return redirect(
                "engagement_work_area_schedule",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_work_area_schedule",
            engagement_pk=engagement.pk,
            work_area_pk=work_area.pk,
        )

    schedule_rows = work_area.schedule_rows.all()
    return render(
        request,
        "engagements/engagement_work_area_schedule.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "schedule_rows": schedule_rows,
        },
    )


def _ensure_engagement_schedule_from_work_area_plan(
    *, engagement, planned_start, planned_finish, user
):
    if not planned_start or not planned_finish:
        return
    if engagement.schedules.exists():
        return
    EngagementSchedule.objects.create(
        engagement=engagement,
        planned_start=planned_start,
        planned_finish=planned_finish,
        actual_start=None,
        actual_finish=None,
        created_by=user,
    )


def _engagement_work_area_schedule_form_view(request, engagement, work_area, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = EngagementWorkAreaPeriodForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            with transaction.atomic():
                schedule_row = form.save(commit=False)
                if not _can_manage_structure(request.user) and instance is not None:
                    schedule_row.planned_start = original_planned_start
                    schedule_row.planned_finish = original_planned_finish
                if (
                    instance is not None
                    and not request.user.is_superuser
                    and had_actual_finish
                    and schedule_row.actual_finish is None
                    and not work_area.schedule_rows.exclude(pk=instance.pk).filter(
                        actual_finish__isnull=False
                    ).exists()
                ):
                    messages.error(
                        request,
                        "Admin only: reopen closed work area.",
                    )
                    return redirect(
                        "engagement_work_area_schedule",
                        engagement_pk=engagement.pk,
                        work_area_pk=work_area.pk,
                    )
                if instance is None:
                    schedule_row.work_area = work_area
                    schedule_row.created_by = request.user
                _ensure_engagement_schedule_from_work_area_plan(
                    engagement=engagement,
                    planned_start=schedule_row.planned_start,
                    planned_finish=schedule_row.planned_finish,
                    user=request.user,
                )
                schedule_row.save()
            return redirect(
                "engagement_work_area_schedule",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = EngagementWorkAreaPeriodForm(instance=instance, work_area=work_area)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    return render(
        request,
        "engagements/engagement_work_area_schedule_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": work_area,
            "schedule_row": instance,
        },
    )


@login_required
def engagement_work_area_schedule_create(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    return _engagement_work_area_schedule_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
    )


@login_required
def engagement_work_area_schedule_edit(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    schedule_row = get_object_or_404(
        EngagementWorkAreaPeriod,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_work_area_schedule_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
        instance=schedule_row,
    )


@login_required
def engagement_work_area_documents(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
    files_redirect = redirect(
        "engagement_work_area_documents",
        engagement_pk=engagement.pk,
        work_area_pk=work_area.pk,
    )
    doc_options = EngagementDocumentation.objects.order_by(
        "standard_document", "document_stage"
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit_document":
            doc = get_object_or_404(
                EngagementWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            documentation_id = (request.POST.get("documentation_id") or "").strip()
            if doc_date is None:
                messages.error(request, "Document date is required.")
                return files_redirect
            if documentation_id:
                documentation = EngagementDocumentation.objects.filter(
                    pk=documentation_id
                ).first()
                if documentation is None:
                    messages.error(request, "Selected documentation is invalid.")
                    return files_redirect
                doc.description = documentation.standard_document
            doc.document_date = doc_date
            doc.document_reference_no = (
                request.POST.get("document_reference_no") or ""
            ).strip()[:100]
            doc.remarks = (request.POST.get("remarks") or "").strip()
            doc.save()
            messages.success(request, "Document details updated.")
            return files_redirect
        if action == "delete_document":
            doc = get_object_or_404(
                EngagementWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc.delete()
            messages.success(request, "Document removed.")
            return files_redirect
        return files_redirect

    documents = work_area.documents.order_by("-document_date", "original_filename", "pk")
    note_attachments = (
        AuditQueryAttachment.objects.filter(query__engagement_work_area=work_area)
        .select_related("query", "created_by")
        .order_by("-created_on", "pk")
    )
    return render(
        request,
        "engagements/engagement_work_area_documents.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "documents": documents,
            "note_attachments": note_attachments,
            "doc_options": doc_options,
        },
    )


def _apply_edit_query_post(request, query):
    """Shared 'edit note' handler for engagement and division work area notes."""
    subject = (request.POST.get("subject") or "").strip()
    amount_raw = (request.POST.get("amount") or "").strip()
    amount_unit = (request.POST.get("amount_unit") or "").strip().lower()
    query_text = (request.POST.get("query_text") or "").strip()
    expected = (request.POST.get("response_expected_from") or "").strip().lower()
    query_date_raw = (request.POST.get("query_date") or "").strip()
    entry_type = (request.POST.get("entry_type") or "").strip().lower()

    query_date = query.query_date
    if query_date_raw:
        parsed = parse_date(query_date_raw)
        if parsed is None:
            messages.error(request, "Enter a valid note date.")
            return
        query_date = parsed

    if entry_type not in {AuditQuery.ENTRY_TYPE_QUERY, AuditQuery.ENTRY_TYPE_REMARK}:
        entry_type = query.entry_type
    if entry_type != query.entry_type and query.entry_type == AuditQuery.ENTRY_TYPE_QUERY:
        if query.converted_to_working_paper:
            messages.error(
                request,
                "Cannot change the entry type: this query was already converted to a working paper.",
            )
            return
        if query.responses.exists():
            messages.error(
                request,
                "Cannot change the entry type: responses are already recorded against this query.",
            )
            return

    amount = None
    if amount_raw:
        try:
            amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid amount.")
            return
    if expected not in {
        AuditQuery.RESPONDER_INTERNAL,
        AuditQuery.RESPONDER_CLIENT,
    }:
        expected = AuditQuery.RESPONDER_INTERNAL
    if amount_unit not in {
        AuditQuery.AMOUNT_UNIT_LAKHS,
        AuditQuery.AMOUNT_UNIT_RS,
        AuditQuery.AMOUNT_UNIT_CRORES,
    }:
        amount_unit = AuditQuery.AMOUNT_UNIT_LAKHS

    if entry_type == AuditQuery.ENTRY_TYPE_QUERY and not subject:
        messages.error(request, "Query subject cannot be blank.")
        return
    if not query_text:
        messages.error(request, "Query details cannot be blank.")
        return
    if entry_type == AuditQuery.ENTRY_TYPE_REMARK and not subject:
        subject = "Remark"

    query.query_date = query_date
    query.entry_type = entry_type
    query.subject = subject
    query.amount = amount if entry_type == AuditQuery.ENTRY_TYPE_QUERY else None
    query.amount_unit = amount_unit
    query.query_text = query_text
    query.response_expected_from = (
        expected
        if entry_type == AuditQuery.ENTRY_TYPE_QUERY
        else AuditQuery.RESPONDER_INTERNAL
    )
    query.save(
        update_fields=[
            "query_date",
            "entry_type",
            "subject",
            "amount",
            "amount_unit",
            "query_text",
            "response_expected_from",
            "updated_on",
        ]
    )
    messages.success(request, "Note updated.")


@login_required
def engagement_work_area_queries(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea.objects.select_related(
            "engagement__service",
            "service_checklist_work_area",
        ),
        pk=work_area_pk,
        engagement=engagement,
    )

    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = (request.POST.get("action") or "").strip()
        if action == "add_query_batch":
            errs = save_work_area_notes_batch(
                request, work_area, engagement_work_area=True
            )
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Notes saved.")
        elif action == "add_all_checklist_lines":
            created, errs = add_all_checklist_lines_to_notes_log(
                request, work_area, engagement_work_area=True
            )
            for msg in errs:
                messages.error(request, msg)
            if created:
                messages.success(
                    request,
                    f"Added {created} checklist line(s) to the notes log.",
                )
            elif not errs:
                messages.info(request, "All checklist lines are already in the notes log.")
        elif action == "save_query_batch_row":
            try:
                row_index = int((request.POST.get("batch_row_save_index") or "").strip())
            except ValueError:
                row_index = -1
            errs = save_work_area_notes_batch_single_row(
                request, work_area, row_index, engagement_work_area=True
            )
            if batch_save_wants_json(request):
                return json_batch_save_response(ok=not errs, errors=errs)
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Line saved.")
            return redirect(
                "engagement_work_area_queries",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        elif action == "add_response":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            response_date = parse_date((request.POST.get("response_date") or "").strip())
            responder_type = (request.POST.get("responder_type") or "").strip().lower()
            response_text = (request.POST.get("response_text") or "").strip()
            close_query = (request.POST.get("close_query") or "").strip() == "1"
            if responder_type not in {
                AuditQuery.RESPONDER_INTERNAL,
                AuditQuery.RESPONDER_CLIENT,
            }:
                responder_type = AuditQuery.RESPONDER_INTERNAL
            if response_date is None:
                messages.error(request, "Enter a valid response date.")
            elif not response_text:
                messages.error(request, "Response text cannot be blank.")
            else:
                with transaction.atomic():
                    AuditQueryResponse.objects.create(
                        query=query,
                        response_date=response_date,
                        responder_type=responder_type,
                        response_text=response_text,
                        created_by=request.user,
                    )
                    if close_query:
                        query.status = AuditQuery.STATUS_CLOSED
                        query.save(update_fields=["status", "updated_on"])
                messages.success(request, "Response added.")
        elif action == "add_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            upload = request.FILES.get("attachment_file")
            if upload is None:
                messages.error(request, "Select a file to upload.")
            else:
                AuditQueryAttachment.objects.create(
                    query=query,
                    file=upload,
                    original_filename=(upload.name or "file")[:255],
                    document_reference_no=(
                        request.POST.get("document_reference_no") or ""
                    ).strip()[:100],
                    created_by=request.user,
                )
                messages.success(request, "Document added to query.")
        elif action == "delete_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            attachment = get_object_or_404(
                AuditQueryAttachment,
                pk=request.POST.get("attachment_pk"),
                query=query,
            )
            attachment.delete()
            messages.success(request, "Document deleted.")
        elif action == "edit_query":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            _apply_edit_query_post(request, query)
        elif action == "delete_query":
            query_pk = (request.POST.get("query_pk") or "").strip()
            if not query_pk:
                messages.error(request, "Select a previous query to delete.")
            else:
                query = get_object_or_404(
                    AuditQuery, pk=query_pk, engagement_work_area=work_area
                )
                query.delete()
                messages.success(request, "Note deleted.")
        elif action == "convert_to_working_paper":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            if query.entry_type != AuditQuery.ENTRY_TYPE_QUERY:
                messages.info(request, "Only query entries can be converted.")
            elif not query.converted_to_working_paper:
                query.converted_to_working_paper = True
                query.working_paper_no = f"AWP-Q{query.pk:06d}"
                query.converted_on = timezone.now()
                query.save(
                    update_fields=[
                        "converted_to_working_paper",
                        "working_paper_no",
                        "converted_on",
                        "updated_on",
                    ]
                )
                messages.success(
                    request,
                    f"Converted to working paper: {query.working_paper_no}",
                )
            else:
                messages.info(
                    request,
                    f"Already converted as {query.working_paper_no}.",
                )
        return redirect(
            "engagement_work_area_queries",
            engagement_pk=engagement.pk,
            work_area_pk=work_area.pk,
        )

    queries = list(
        work_area.audit_queries.select_related(
            "created_by", "service_checklist_item"
        )
        .prefetch_related("responses__created_by", "attachments")
        .all()
    )
    ctx = work_area_notes_page_context(
        work_area,
        queries,
        engagement=engagement,
        engagement_work_area=True,
    )
    ctx["default_date"] = timezone.localdate()
    return render(request, "engagements/work_area_queries.html", ctx)


@login_required
@require_GET
def engagement_work_area_document_download(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    doc = get_object_or_404(
        EngagementWorkAreaDocument.objects.select_related("work_area__engagement"),
        pk=pk,
        work_area_id=work_area_pk,
        work_area__engagement_id=engagement.pk,
    )
    if not doc.file:
        raise Http404
    safe_name = get_valid_filename(doc.original_filename) or "download"
    try:
        file_handle = doc.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
@require_GET
def engagement_query_attachment_download(
    request, engagement_pk, work_area_pk, query_pk, pk
):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    attachment = get_object_or_404(
        AuditQueryAttachment.objects.select_related("query__engagement_work_area__engagement"),
        pk=pk,
        query_id=query_pk,
        query__engagement_work_area_id=work_area_pk,
        query__engagement_work_area__engagement_id=engagement.pk,
    )
    if not attachment.file:
        raise Http404
    safe_name = get_valid_filename(attachment.original_filename) or "download"
    try:
        file_handle = attachment.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
def engagement_division_work_areas(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    eligible_source_divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .exclude(pk=division.pk)
        .filter(
            engagement__client_id=division.engagement.client_id,
            engagement__service_id=division.engagement.service_id,
            engagement__fiscal_year_id=division.engagement.fiscal_year_id,
        )
    )
    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    assert_division_open_for_management(request.user, division)

    def _division_work_areas_redirect():
        base = reverse(
            "engagement_division_work_areas", kwargs={"division_pk": division.pk}
        )
        if raw_status == "all":
            return redirect(f"{base}?{urlencode({'status': raw_status})}")
        return redirect(base)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            work_area = get_object_or_404(
                DivisionWorkArea,
                pk=request.POST.get("pk"),
                division=division,
            )
            work_area.delete()
            return _division_work_areas_redirect()
        if action == "add_from_service_templates":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            raw_ids = []
            for raw in request.POST.getlist("service_work_area_ids"):
                try:
                    raw_ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
            raw_ids = list(dict.fromkeys(raw_ids))
            created = _add_division_work_areas_from_service_templates(
                request, division, raw_ids
            )
            if created:
                messages.success(
                    request,
                    f"Added {created} work area(s) from the service standard list.",
                )
            else:
                messages.info(
                    request,
                    "No new work areas were added (none selected, or all were already present).",
                )
            return _division_work_areas_redirect()
        if action == "copy_from_division":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            source_division_id = (request.POST.get("source_division_id") or "").strip()
            if not source_division_id:
                messages.error(request, "Select a source division.")
                return _division_work_areas_redirect()
            source_division = eligible_source_divisions.filter(pk=source_division_id).first()
            if source_division is None:
                messages.error(
                    request,
                    "Selected source division is invalid. Choose one with the same client, service, and fiscal year.",
                )
                return _division_work_areas_redirect()

            with transaction.atomic():
                existing_names = {
                    name.strip().casefold()
                    for name in DivisionWorkArea.objects.filter(division=division).values_list(
                        "work_area_name", flat=True
                    )
                }
                source_work_areas = source_division.work_areas.order_by("sort_order", "id")
                created_count = 0
                for source_work_area in source_work_areas:
                    normalized = (source_work_area.work_area_name or "").strip().casefold()
                    if not normalized or normalized in existing_names:
                        continue
                    DivisionWorkArea.objects.create(
                        division=division,
                        work_area_name=source_work_area.work_area_name,
                        sort_order=9999,
                        created_by=request.user,
                    )
                    existing_names.add(normalized)
                    created_count += 1

                if created_count:
                    ordered_ids = list(
                        DivisionWorkArea.objects.filter(division=division)
                        .order_by("sort_order", "id")
                        .values_list("pk", flat=True)
                    )
                    for idx, pk in enumerate(ordered_ids, start=1):
                        DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)
            if created_count:
                messages.success(
                    request,
                    f"Copied {created_count} work area(s) from {source_division.division_name}.",
                )
            else:
                messages.info(
                    request,
                    "No new work areas to copy from the selected division.",
                )
            return _division_work_areas_redirect()
        if action == "send_confirmation_mail":
            team_mail.manual_notify_division_work_area_confirmation_mail(
                request, division
            )
            return _division_work_areas_redirect()
        if action == "send_confirmation_mail_repeat":
            team_mail.manual_notify_division_work_area_confirmation_mail_repeat(
                request, division
            )
            return _division_work_areas_redirect()
        if action == "bulk_add_all_standard":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            service_template_list = list(
                _service_checklist_templates_for_service(division.engagement.service_id)
            )
            all_service_pick_rows = _division_service_work_area_pick_rows(
                division, service_template_list
            )
            stats = _bulk_add_all_standard_work_areas(
                request,
                division=division,
                pick_rows=all_service_pick_rows,
            )
            msg = (
                f"Added {stats['work_areas_added']} work area(s) and "
                f"{stats['checklist_lines_added']} checklist line(s) to the notes log."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _division_work_areas_redirect()
        if action == "bulk_delete_all_without_queries":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            stats = _bulk_delete_work_areas_without_queries(division=division)
            msg = (
                f"Deleted {stats['deleted']} work area(s). "
                f"Kept {stats['skipped_with_queries']} with notes/queries."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _division_work_areas_redirect()
        return _division_work_areas_redirect()

    work_areas = (
        _division_work_area_queryset_for_user(request.user)
        .filter(division=division)
        .annotate(
            schedule_row_count=Count("schedule_rows"),
            document_count=Count("documents"),
            assignment_count=Count("team_assignments"),
            status_remark_count=Count("status_remarks"),
        )
        .order_by("work_area_name", "sort_order", "id")
    )
    if raw_status == "active":
        work_areas = work_areas.exclude(status=STATUS_COMPLETED)
    source_divisions = eligible_source_divisions.order_by(
        "engagement__client__client_name",
        "-engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "division_name",
    )
    service_template_list = list(
        _service_checklist_templates_for_service(division.engagement.service_id)
    )
    all_service_pick_rows = _division_service_work_area_pick_rows(
        division, service_template_list
    )
    service_work_area_pick_rows = [
        r for r in all_service_pick_rows if not r["already_added"]
    ]
    service_standard_template_count = len(service_template_list)
    return render(
        request,
        "engagements/engagement_division_work_areas.html",
        {
            "division": division,
            "work_areas": work_areas,
            "source_divisions": source_divisions,
            "work_area_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
            "service_work_area_pick_rows": service_work_area_pick_rows,
            "service_standard_template_count": service_standard_template_count,
        },
    )


@login_required
def engagement_division_work_area_notes_list(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    rows = (
        AuditQuery.objects.filter(division_work_area__division=division)
        .select_related("division_work_area")
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    ctx = work_area_notes_list_page_context(
        engagement=division.engagement,
        division=division,
        rows=rows,
    )
    return render(request, "engagements/work_area_notes_list.html", ctx)


@login_required
def engagement_division_work_area_assignments(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            assignment = get_object_or_404(
                DivisionWorkAreaTeamAssignment,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            assignment.delete()
            return redirect(
                "engagement_division_work_area_assignments",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_division_work_area_assignments",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    assignments = work_area.team_assignments.select_related("team_member")
    return render(
        request,
        "engagements/engagement_division_work_area_assignments.html",
        {
            "division": division,
            "work_area": work_area,
            "assignments": assignments,
        },
    )


def _engagement_division_work_area_assignment_form_view(
    request, division, work_area, instance=None
):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = DivisionWorkAreaTeamAssignmentForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.work_area = work_area
                assignment.created_by = request.user
            assignment.save()
            return redirect(
                "engagement_division_work_area_assignments",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = DivisionWorkAreaTeamAssignmentForm(
            instance=instance, work_area=work_area
        )
    return render(
        request,
        "engagements/engagement_division_work_area_assignment_form.html",
        {
            "form": form,
            "division": division,
            "work_area": work_area,
            "assignment": instance,
        },
    )


@login_required
def engagement_division_work_area_assignment_create(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    return _engagement_division_work_area_assignment_form_view(
        request, division=division, work_area=work_area
    )


@login_required
def engagement_division_work_area_assignment_edit(
    request, division_pk, work_area_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    assignment = get_object_or_404(
        DivisionWorkAreaTeamAssignment,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_division_work_area_assignment_form_view(
        request,
        division=division,
        work_area=work_area,
        instance=assignment,
    )


@login_required
def engagement_division_work_area_documents(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    files_redirect = redirect(
        "engagement_division_work_area_documents",
        division_pk=division.pk,
        work_area_pk=work_area.pk,
    )
    doc_options = EngagementDocumentation.objects.order_by(
        "standard_document", "document_stage"
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "edit_document":
            doc = get_object_or_404(
                DivisionWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            documentation_id = (request.POST.get("documentation_id") or "").strip()
            if doc_date is None:
                messages.error(request, "Document date is required.")
                return files_redirect
            if documentation_id:
                documentation = EngagementDocumentation.objects.filter(
                    pk=documentation_id
                ).first()
                if documentation is None:
                    messages.error(request, "Selected documentation is invalid.")
                    return files_redirect
                doc.description = documentation.standard_document
            doc.document_date = doc_date
            doc.document_reference_no = (
                request.POST.get("document_reference_no") or ""
            ).strip()[:100]
            doc.remarks = (request.POST.get("remarks") or "").strip()
            doc.save()
            messages.success(request, "Document details updated.")
            return files_redirect
        if action == "delete_document":
            doc = get_object_or_404(
                DivisionWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc.delete()
            messages.success(request, "Document removed.")
            return files_redirect
        return files_redirect

    documents = work_area.documents.order_by("-document_date", "original_filename", "pk")
    note_attachments = (
        AuditQueryAttachment.objects.filter(query__division_work_area=work_area)
        .select_related("query", "created_by")
        .order_by("-created_on", "pk")
    )
    return render(
        request,
        "engagements/engagement_division_work_area_documents.html",
        {
            "division": division,
            "work_area": work_area,
            "documents": documents,
            "note_attachments": note_attachments,
            "doc_options": doc_options,
        },
    )


@login_required
def engagement_division_work_area_queries(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea.objects.select_related(
            "division__engagement__service",
            "service_checklist_work_area",
        ),
        pk=work_area_pk,
        division=division,
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = (request.POST.get("action") or "").strip()
        if action == "add_query_batch":
            errs = save_work_area_notes_batch(
                request, work_area, engagement_work_area=False
            )
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Notes saved.")
        elif action == "add_all_checklist_lines":
            created, errs = add_all_checklist_lines_to_notes_log(
                request, work_area, engagement_work_area=False
            )
            for msg in errs:
                messages.error(request, msg)
            if created:
                messages.success(
                    request,
                    f"Added {created} checklist line(s) to the notes log.",
                )
            elif not errs:
                messages.info(request, "All checklist lines are already in the notes log.")
        elif action == "save_query_batch_row":
            try:
                row_index = int((request.POST.get("batch_row_save_index") or "").strip())
            except ValueError:
                row_index = -1
            errs = save_work_area_notes_batch_single_row(
                request, work_area, row_index, engagement_work_area=False
            )
            if batch_save_wants_json(request):
                return json_batch_save_response(ok=not errs, errors=errs)
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Line saved.")
            return redirect(
                "engagement_division_work_area_queries",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        elif action == "add_response":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            response_date = parse_date((request.POST.get("response_date") or "").strip())
            responder_type = (request.POST.get("responder_type") or "").strip().lower()
            response_text = (request.POST.get("response_text") or "").strip()
            close_query = (request.POST.get("close_query") or "").strip() == "1"
            if responder_type not in {
                AuditQuery.RESPONDER_INTERNAL,
                AuditQuery.RESPONDER_CLIENT,
            }:
                responder_type = AuditQuery.RESPONDER_INTERNAL
            if response_date is None:
                messages.error(request, "Enter a valid response date.")
            elif not response_text:
                messages.error(request, "Response text cannot be blank.")
            else:
                with transaction.atomic():
                    AuditQueryResponse.objects.create(
                        query=query,
                        response_date=response_date,
                        responder_type=responder_type,
                        response_text=response_text,
                        created_by=request.user,
                    )
                    if close_query:
                        query.status = AuditQuery.STATUS_CLOSED
                        query.save(update_fields=["status", "updated_on"])
                messages.success(request, "Response added.")
        elif action == "add_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            upload = request.FILES.get("attachment_file")
            if upload is None:
                messages.error(request, "Select a file to upload.")
            else:
                AuditQueryAttachment.objects.create(
                    query=query,
                    file=upload,
                    original_filename=(upload.name or "file")[:255],
                    document_reference_no=(
                        request.POST.get("document_reference_no") or ""
                    ).strip()[:100],
                    created_by=request.user,
                )
                messages.success(request, "Document added to query.")
        elif action == "delete_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            attachment = get_object_or_404(
                AuditQueryAttachment,
                pk=request.POST.get("attachment_pk"),
                query=query,
            )
            attachment.delete()
            messages.success(request, "Document deleted.")
        elif action == "edit_query":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            _apply_edit_query_post(request, query)
        elif action == "delete_query":
            query_pk = (request.POST.get("query_pk") or "").strip()
            if not query_pk:
                messages.error(request, "Select a previous query to delete.")
            else:
                query = get_object_or_404(
                    AuditQuery, pk=query_pk, division_work_area=work_area
                )
                query.delete()
                messages.success(request, "Note deleted.")
        elif action == "convert_to_working_paper":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            if query.entry_type != AuditQuery.ENTRY_TYPE_QUERY:
                messages.info(request, "Only query entries can be converted.")
            elif not query.converted_to_working_paper:
                query.converted_to_working_paper = True
                query.working_paper_no = f"AWP-Q{query.pk:06d}"
                query.converted_on = timezone.now()
                query.save(
                    update_fields=[
                        "converted_to_working_paper",
                        "working_paper_no",
                        "converted_on",
                        "updated_on",
                    ]
                )
                messages.success(
                    request,
                    f"Converted to working paper: {query.working_paper_no}",
                )
            else:
                messages.info(
                    request,
                    f"Already converted as {query.working_paper_no}.",
                )
        return redirect(
            "engagement_division_work_area_queries",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    queries = list(
        work_area.audit_queries.select_related(
            "created_by", "service_checklist_item"
        )
        .prefetch_related("responses__created_by", "attachments")
        .all()
    )
    ctx = work_area_notes_page_context(
        work_area,
        queries,
        engagement=division.engagement,
        division=division,
        engagement_work_area=False,
    )
    ctx["default_date"] = timezone.localdate()
    return render(request, "engagements/work_area_queries.html", ctx)


@login_required
@require_GET
def engagement_division_work_area_document_download(
    request, division_pk, work_area_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    doc = get_object_or_404(
        DivisionWorkAreaDocument.objects.select_related("work_area__division"),
        pk=pk,
        work_area_id=work_area_pk,
        work_area__division_id=division.pk,
    )
    if not doc.file:
        raise Http404
    safe_name = get_valid_filename(doc.original_filename) or "download"
    try:
        file_handle = doc.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
@require_GET
def engagement_division_query_attachment_download(
    request, division_pk, work_area_pk, query_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    attachment = get_object_or_404(
        AuditQueryAttachment.objects.select_related("query__division_work_area__division"),
        pk=pk,
        query_id=query_pk,
        query__division_work_area_id=work_area_pk,
        query__division_work_area__division_id=division.pk,
    )
    if not attachment.file:
        raise Http404
    safe_name = get_valid_filename(attachment.original_filename) or "download"
    try:
        file_handle = attachment.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
def engagement_status_remarks(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client",
            "fiscal_year",
            "service",
        ),
        pk=engagement_pk,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = (request.POST.get("action") or "").strip()
        if action == "add_remark":
            remarks = (request.POST.get("remarks") or "").strip()
            remark_date = parse_date((request.POST.get("remark_date") or "").strip())
            if remark_date is None:
                messages.error(request, "Enter a valid status remark date.")
            elif not remarks:
                messages.error(request, "Remarks cannot be blank.")
            else:
                EngagementStatusRemark.objects.create(
                    engagement=engagement,
                    remark_date=remark_date,
                    remarks=remarks,
                    created_by=request.user,
                )
                messages.success(request, "Status remark added.")
        return redirect("engagement_status_remarks", engagement_pk=engagement.pk)

    remarks = engagement.status_remarks.select_related("created_by").all()
    team_assignments = engagement.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_status_remarks.html",
        {
            "engagement": engagement,
            "remarks": remarks,
            "team_assignments": team_assignments,
            "default_remark_date": timezone.localdate(),
        },
    )


@login_required
def engagement_division_status_remarks(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = (request.POST.get("action") or "").strip()
        if action == "add_remark":
            remarks = (request.POST.get("remarks") or "").strip()
            remark_date = parse_date((request.POST.get("remark_date") or "").strip())
            if remark_date is None:
                messages.error(request, "Enter a valid status remark date.")
            elif not remarks:
                messages.error(request, "Remarks cannot be blank.")
            else:
                EngagementDivisionStatusRemark.objects.create(
                    division=division,
                    remark_date=remark_date,
                    remarks=remarks,
                    created_by=request.user,
                )
                messages.success(request, "Status remark added.")
        return redirect("engagement_division_status_remarks", division_pk=division.pk)

    remarks = division.status_remarks.select_related("created_by").all()
    team_assignments = division.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_division_status_remarks.html",
        {
            "division": division,
            "remarks": remarks,
            "team_assignments": team_assignments,
            "default_remark_date": timezone.localdate(),
        },
    )


@login_required
def engagement_work_area_status_remarks(request, engagement_pk, work_area_pk):
    return redirect(
        "engagement_work_area_queries",
        engagement_pk=engagement_pk,
        work_area_pk=work_area_pk,
    )


@login_required
def engagement_division_work_area_status_remarks(request, division_pk, work_area_pk):
    return redirect(
        "engagement_division_work_area_queries",
        division_pk=division_pk,
        work_area_pk=work_area_pk,
    )


def _division_work_area_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = DivisionWorkAreaForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            with transaction.atomic():
                work_area = form.save(commit=False)
                if instance is None:
                    work_area.division = division
                    work_area.created_by = request.user
                work_area.save()
                _resequence_scoped_work_areas(
                    model=DivisionWorkArea,
                    scope_filter={"division": division},
                    target_pk=work_area.pk,
                    requested_order=form.cleaned_data.get("sort_order"),
                )
            return redirect(
                "engagement_division_work_areas",
                division_pk=division.pk,
            )
    else:
        form = DivisionWorkAreaForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_work_area_form.html",
        {
            "form": form,
            "division": division,
            "work_area": instance,
        },
    )


@login_required
def engagement_division_work_area_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    return _division_work_area_form_view(request, division=division)


@login_required
def engagement_division_work_area_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=pk,
        division=division,
    )
    return _division_work_area_form_view(
        request,
        division=division,
        instance=work_area,
    )


@login_required
def engagement_division_work_area_schedule(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            schedule_row = get_object_or_404(
                DivisionWorkAreaPeriod,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            if (
                not request.user.is_superuser
                and schedule_row.actual_finish is not None
                and not work_area.schedule_rows.exclude(pk=schedule_row.pk).filter(
                    actual_finish__isnull=False
                ).exists()
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed work area.",
                )
                return redirect(
                    "engagement_division_work_area_schedule",
                    division_pk=division.pk,
                    work_area_pk=work_area.pk,
                )
            schedule_row.delete()
            return redirect(
                "engagement_division_work_area_schedule",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_division_work_area_schedule",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    schedule_rows = work_area.schedule_rows.all()
    return render(
        request,
        "engagements/engagement_division_work_area_schedule.html",
        {
            "division": division,
            "work_area": work_area,
            "schedule_rows": schedule_rows,
        },
    )


def _division_work_area_schedule_form_view(request, division, work_area, instance=None):
    assert_division_open_for_management(request.user, division)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = DivisionWorkAreaPeriodForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            with transaction.atomic():
                schedule_row = form.save(commit=False)
                if not _can_manage_structure(request.user) and instance is not None:
                    schedule_row.planned_start = original_planned_start
                    schedule_row.planned_finish = original_planned_finish
                if (
                    instance is not None
                    and not request.user.is_superuser
                    and had_actual_finish
                    and schedule_row.actual_finish is None
                    and not work_area.schedule_rows.exclude(pk=instance.pk).filter(
                        actual_finish__isnull=False
                    ).exists()
                ):
                    messages.error(
                        request,
                        "Admin only: reopen closed work area.",
                    )
                    return redirect(
                        "engagement_division_work_area_schedule",
                        division_pk=division.pk,
                        work_area_pk=work_area.pk,
                    )
                if instance is None:
                    schedule_row.work_area = work_area
                    schedule_row.created_by = request.user
                _ensure_engagement_schedule_from_work_area_plan(
                    engagement=division.engagement,
                    planned_start=schedule_row.planned_start,
                    planned_finish=schedule_row.planned_finish,
                    user=request.user,
                )
                schedule_row.save()
            return redirect(
                "engagement_division_work_area_schedule",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = DivisionWorkAreaPeriodForm(instance=instance, work_area=work_area)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    return render(
        request,
        "engagements/engagement_division_work_area_schedule_form.html",
        {
            "form": form,
            "division": division,
            "work_area": work_area,
            "schedule_row": instance,
        },
    )


@login_required
def engagement_division_work_area_schedule_create(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    return _division_work_area_schedule_form_view(
        request,
        division=division,
        work_area=work_area,
    )


@login_required
def engagement_division_work_area_schedule_edit(request, division_pk, work_area_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    schedule_row = get_object_or_404(
        DivisionWorkAreaPeriod,
        pk=pk,
        work_area=work_area,
    )
    return _division_work_area_schedule_form_view(
        request,
        division=division,
        work_area=work_area,
        instance=schedule_row,
    )


@login_required
def engagement_documentation_maps(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = request.POST.get("action")
        if action == "delete":
            documentation_map = get_object_or_404(
                EngagementDocumentationMap,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            documentation_map.delete()
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        if action == "delete_all_documentation_maps":
            qs = engagement.documentation_maps.all()
            n = qs.count()
            if n:
                with transaction.atomic():
                    qs.delete()
                messages.success(
                    request,
                    (
                        f"Removed {n} documentation mapping(s) for this engagement "
                        "(including uploaded files under each mapping)."
                    ),
                )
            else:
                messages.info(request, "No documentation mappings to remove.")
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        if action == "prefill_from_client_classification":
            classification = engagement.client.classification
            applicable_docs = (
                EngagementDocumentation.objects.filter(
                    applicable_classifications=classification
                )
                .distinct()
                .order_by("document_stage", "standard_document")
            )
            existing_ids = set(
                engagement.documentation_maps.values_list(
                    "documentation_id", flat=True
                )
            )
            today = timezone.localdate()
            new_maps = [
                EngagementDocumentationMap(
                    engagement=engagement,
                    documentation=doc,
                    documentation_date=today,
                    created_by=request.user,
                )
                for doc in applicable_docs
                if doc.id not in existing_ids
            ]
            if new_maps:
                with transaction.atomic():
                    EngagementDocumentationMap.objects.bulk_create(new_maps)
                messages.success(
                    request,
                    (
                        f"Added {len(new_maps)} documentation mapping(s) that apply to "
                        f"{classification.classification_name}. Remove any you do not need."
                    ),
                )
            else:
                messages.info(
                    request,
                    (
                        "No new mappings were added. Either every matching item is already "
                        "mapped, or no setup documentation lists this client's classification "
                        "under Applicable To."
                    ),
                )
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)

    attachment_qs = EngagementDocumentationMapAttachment.objects.order_by(
        "-document_date", "original_filename", "pk"
    )
    documentation_maps = (
        engagement.documentation_maps.select_related("documentation")
        .annotate(
            attachment_count=Count("attachments", distinct=True),
            has_setup_word_template=Exists(
                EngagementDocumentation.objects.filter(
                    pk=OuterRef("documentation_id"),
                )
                .exclude(word_template__isnull=True)
                .exclude(word_template="")
            ),
        )
        .prefetch_related(Prefetch("attachments", queryset=attachment_qs))
        .order_by(
            "documentation_date",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    return render(
        request,
        "engagements/engagement_documentation_maps.html",
        {
            "engagement": engagement,
            "documentation_maps": documentation_maps,
        },
    )


@login_required
def engagement_documentation_missing_uploads_report(request, engagement_pk):
    """Mapped engagement + division documentation with no uploaded files yet."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    missing_rows = []
    eng_maps = (
        engagement.documentation_maps.select_related("documentation")
        .annotate(_ac=Count("attachments", distinct=True))
        .filter(_ac=0)
        .order_by(
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    for m in eng_maps:
        missing_rows.append(
            {
                "scope_label": "Engagement",
                "standard_document": m.documentation.standard_document,
                "stage_display": m.documentation.get_document_stage_display(),
                "document_stage": m.documentation.document_stage,
                "list_date": m.documentation_date,
                "files_url": reverse(
                    "engagement_documentation_map_files",
                    kwargs={"engagement_pk": engagement.pk, "map_pk": m.pk},
                ),
            }
        )
    div_maps = (
        EngagementDivisionDocumentationMap.objects.filter(
            division__engagement=engagement,
        )
        .select_related("documentation", "division")
        .annotate(_ac=Count("attachments", distinct=True))
        .filter(_ac=0)
        .order_by(
            "division__division_name",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    for m in div_maps:
        missing_rows.append(
            {
                "scope_label": f"Division: {m.division.division_name}",
                "standard_document": m.documentation.standard_document,
                "stage_display": m.documentation.get_document_stage_display(),
                "document_stage": m.documentation.document_stage,
                "list_date": None,
                "files_url": reverse(
                    "engagement_division_documentation_map_files",
                    kwargs={"division_pk": m.division_id, "map_pk": m.pk},
                ),
            }
        )
    missing_rows.sort(
        key=lambda r: (
            r["document_stage"],
            (r["standard_document"] or "").casefold(),
            r["scope_label"],
        )
    )
    return render(
        request,
        "engagements/engagement_documentation_missing_uploads_report.html",
        {
            "engagement": engagement,
            "missing_rows": missing_rows,
        },
    )


def _handle_engagement_duplicate_document_delete(request, engagement) -> bool:
    """Shared delete_duplicate POST handler. Returns True if the POST was handled."""
    if request.method != "POST" or request.POST.get("action") != "delete_duplicate":
        return False
    assert_engagement_open_for_management(request.user, engagement)
    source_kind = (request.POST.get("source_kind") or "").strip()
    pk_raw = (request.POST.get("pk") or "").strip()
    if not pk_raw.isdigit():
        messages.error(request, "Invalid duplicate selection.")
        return True
    row_id = int(pk_raw)
    deleted = False
    if source_kind == "engagement_attachment":
        deleted, _ = EngagementDocumentationMapAttachment.objects.filter(
            pk=row_id,
            documentation_map__engagement=engagement,
        ).delete()
    elif source_kind == "division_attachment":
        deleted, _ = EngagementDivisionDocumentationMapAttachment.objects.filter(
            pk=row_id,
            documentation_map__division__engagement=engagement,
        ).delete()
    elif source_kind == "engagement_work_area_doc":
        deleted, _ = EngagementWorkAreaDocument.objects.filter(
            pk=row_id,
            work_area__engagement=engagement,
        ).delete()
    elif source_kind == "division_work_area_doc":
        deleted, _ = DivisionWorkAreaDocument.objects.filter(
            pk=row_id,
            work_area__division__engagement=engagement,
        ).delete()
    elif source_kind == "audit_query_engagement_attachment":
        deleted, _ = AuditQueryAttachment.objects.filter(
            pk=row_id,
            query__engagement_work_area__engagement=engagement,
        ).delete()
    elif source_kind == "audit_query_division_attachment":
        deleted, _ = AuditQueryAttachment.objects.filter(
            pk=row_id,
            query__division_work_area__division__engagement=engagement,
        ).delete()
    if deleted:
        messages.success(request, "Duplicate file removed.")
    else:
        messages.error(request, "Unable to remove the selected duplicate.")
    return True


def _engagement_uploaded_document_rows(engagement):
    rows = []
    engagement_attachments = EngagementDocumentationMapAttachment.objects.select_related(
        "documentation_map__documentation"
    ).filter(documentation_map__engagement=engagement)
    for att in engagement_attachments:
        doc = att.documentation_map.documentation
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_level": "Engagement",
                "source_name": "Engagement documentation",
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_documentation_attachment_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "engagement_attachment",
                "pk": att.pk,
                "division_scope": "engagement",
                "reference_no": "",
                "remarks": "",
            }
        )

    division_attachments = (
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division", "documentation_map__documentation"
        )
        .filter(documentation_map__division__engagement=engagement)
        .all()
    )
    for att in division_attachments:
        doc = att.documentation_map.documentation
        division = att.documentation_map.division
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_level": "Division",
                "source_name": division.division_name,
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_documentation_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "division_attachment",
                "pk": att.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": "",
                "remarks": "",
            }
        )

    engagement_work_area_docs = EngagementWorkAreaDocument.objects.select_related(
        "work_area"
    ).filter(work_area__engagement=engagement)
    for doc in engagement_work_area_docs:
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_level": "Eng. work area",
                "source_name": doc.work_area.work_area_name,
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_work_area_document_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "engagement_work_area_doc",
                "pk": doc.pk,
                "division_scope": "engagement",
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    division_work_area_docs = DivisionWorkAreaDocument.objects.select_related(
        "work_area__division"
    ).filter(work_area__division__engagement=engagement)
    for doc in division_work_area_docs:
        division = doc.work_area.division
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_level": "Div. work area",
                "source_name": f"{division.division_name} / {doc.work_area.work_area_name}",
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_division_work_area_document_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "division_work_area_doc",
                "pk": doc.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    audit_eng_attachments = (
        AuditQueryAttachment.objects.select_related(
            "query__engagement_work_area",
        )
        .filter(query__engagement_work_area__engagement=engagement)
        .order_by("-created_on", "pk")
    )
    for att in audit_eng_attachments:
        wa = att.query.engagement_work_area
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_level": "Eng. WA query",
                "source_name": wa.work_area_name,
                "document_label": (att.query.subject or "").strip() or "Query note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_query_attachment_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_engagement_attachment",
                "pk": att.pk,
                "division_scope": "engagement",
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    audit_div_attachments = (
        AuditQueryAttachment.objects.select_related(
            "query__division_work_area__division",
        )
        .filter(query__division_work_area__division__engagement=engagement)
        .order_by("-created_on", "pk")
    )
    for att in audit_div_attachments:
        wa = att.query.division_work_area
        division = wa.division
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_level": "Div. WA query",
                "source_name": f"{division.division_name} / {wa.work_area_name}",
                "document_label": (att.query.subject or "").strip() or "Query note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_query_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_division_attachment",
                "pk": att.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    duplicate_groups = defaultdict(int)
    for row in rows:
        duplicate_groups[
            (
                row.get("division_scope"),
                (row.get("file_name") or "").strip().casefold(),
            )
        ] += 1
    for row in rows:
        key = (
            row.get("division_scope"),
            (row.get("file_name") or "").strip().casefold(),
        )
        row["duplicate_count"] = duplicate_groups[key]
        row["is_duplicate"] = duplicate_groups[key] > 1

    rows.sort(
        key=lambda item: (
            item["document_date"] or timezone.localdate(),
            item["created_on"] or timezone.now(),
            item["file_name"],
        ),
        reverse=True,
    )
    return rows


@login_required
def engagement_uploaded_documents_report(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if _handle_engagement_duplicate_document_delete(request, engagement):
        return redirect(
            "engagement_uploaded_documents_report", engagement_pk=engagement.pk
        )
    return render(
        request,
        "engagements/engagement_uploaded_documents_report.html",
        {
            "engagement": engagement,
            "rows": _engagement_uploaded_document_rows(engagement),
        },
    )


@login_required
def engagement_documents_and_notes(request, engagement_pk):
    """Combined report: work area notes plus every uploaded document for one engagement."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if _handle_engagement_duplicate_document_delete(request, engagement):
        return redirect("engagement_documents_and_notes", engagement_pk=engagement.pk)
    note_rows = (
        AuditQuery.objects.filter(
            Q(engagement_work_area__engagement=engagement)
            | Q(division_work_area__division__engagement=engagement)
        )
        .select_related(
            "engagement_work_area",
            "division_work_area__division",
        )
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    return render(
        request,
        "engagements/engagement_documents_and_notes.html",
        {
            "engagement": engagement,
            "note_rows": note_rows,
            "document_rows": _engagement_uploaded_document_rows(engagement),
        },
    )


@login_required
def engagement_division_uploaded_documents_report(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    rows = []
    if request.method == "POST" and request.POST.get("action") == "delete_duplicate":
        assert_division_open_for_management(request.user, division)
        source_kind = (request.POST.get("source_kind") or "").strip()
        pk_raw = (request.POST.get("pk") or "").strip()
        if not pk_raw.isdigit():
            messages.error(request, "Invalid duplicate selection.")
            return redirect(
                "engagement_division_uploaded_documents_report",
                division_pk=division.pk,
            )
        row_id = int(pk_raw)
        deleted = False
        if source_kind == "division_attachment":
            deleted, _ = EngagementDivisionDocumentationMapAttachment.objects.filter(
                pk=row_id,
                documentation_map__division=division,
            ).delete()
        elif source_kind == "division_work_area_doc":
            deleted, _ = DivisionWorkAreaDocument.objects.filter(
                pk=row_id,
                work_area__division=division,
            ).delete()
        if deleted:
            messages.success(request, "Duplicate file removed.")
        else:
            messages.error(request, "Unable to remove the selected duplicate.")
        return redirect(
            "engagement_division_uploaded_documents_report",
            division_pk=division.pk,
        )

    division_attachments = (
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__documentation"
        )
        .filter(documentation_map__division=division)
        .all()
    )
    for att in division_attachments:
        doc = att.documentation_map.documentation
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_name": "Division documentation",
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_documentation_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "division_attachment",
                "pk": att.pk,
                "reference_no": "",
                "remarks": "",
            }
        )

    division_work_area_docs = DivisionWorkAreaDocument.objects.select_related(
        "work_area"
    ).filter(work_area__division=division)
    for doc in division_work_area_docs:
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_name": f"Work area: {doc.work_area.work_area_name}",
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_division_work_area_document_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "division_work_area_doc",
                "pk": doc.pk,
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    note_attachments = (
        AuditQueryAttachment.objects.select_related("query__division_work_area")
        .filter(query__division_work_area__division=division)
        .order_by("-created_on", "pk")
    )
    for att in note_attachments:
        wa = att.query.division_work_area
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_name": f"Work area note: {wa.work_area_name}",
                "document_label": (att.query.subject or "").strip() or "Work area note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_query_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_division_attachment",
                "pk": att.pk,
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    duplicate_groups = defaultdict(int)
    for row in rows:
        duplicate_groups[(row.get("file_name") or "").strip().casefold()] += 1
    for row in rows:
        key = (row.get("file_name") or "").strip().casefold()
        row["duplicate_count"] = duplicate_groups[key]
        row["is_duplicate"] = duplicate_groups[key] > 1

    rows.sort(
        key=lambda item: (
            item["document_date"] or timezone.localdate(),
            item["created_on"] or timezone.now(),
            item["file_name"],
        ),
        reverse=True,
    )
    return render(
        request,
        "engagements/engagement_division_uploaded_documents_report.html",
        {
            "division": division,
            "rows": rows,
        },
    )


@login_required
def engagement_documentation_map_files(request, engagement_pk, map_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        engagement=engagement,
    )
    files_redirect = redirect(
        "engagement_documentation_map_files",
        engagement_pk=engagement.pk,
        map_pk=documentation_map.pk,
    )

    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = request.POST.get("action")
        if action == "upload_attachment":
            files = request.FILES.getlist("files")
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            description = (request.POST.get("description") or "").strip()
            if doc_date is None:
                doc_date = documentation_map.documentation_date
            if not files:
                messages.warning(request, "No files were selected.")
            else:
                n = 0
                with transaction.atomic():
                    for upload in files[:30]:
                        EngagementDocumentationMapAttachment.objects.create(
                            documentation_map=documentation_map,
                            file=upload,
                            original_filename=(upload.name or "file")[:255],
                            document_date=doc_date,
                            description=description,
                            created_by=request.user,
                        )
                        n += 1
                messages.success(request, f"Added {n} file(s).")
            return files_redirect
        if action == "delete_attachment":
            attachment = get_object_or_404(
                EngagementDocumentationMapAttachment,
                pk=request.POST.get("pk"),
                documentation_map=documentation_map,
            )
            attachment.delete()
            messages.success(request, "Attachment removed.")
            return files_redirect
        return files_redirect

    attachments = documentation_map.attachments.order_by(
        "-document_date", "original_filename", "pk"
    )
    return render(
        request,
        "engagements/engagement_documentation_map_files.html",
        {
            "engagement": engagement,
            "documentation_map": documentation_map,
            "attachments": attachments,
        },
    )


@login_required
@require_GET
def engagement_documentation_map_word_filled_download(
    request, engagement_pk, map_pk
):
    """Download the setup Word template with ``{{TOKEN}}`` placeholders filled for this engagement."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client",
            "fiscal_year",
            "service",
            "client__classification",
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        engagement=engagement,
    )
    doc_item = documentation_map.documentation
    raw_name = (getattr(doc_item.word_template, "name", None) or "").strip()
    if not raw_name:
        return HttpResponseBadRequest(
            "Fill Word needs a Word template on this standard document in "
            "Setup → Documentation. Open that row, upload a .docx template, save, "
            "then refresh this engagement page and try again."
        )
    if not raw_name.lower().endswith(".docx"):
        return HttpResponseBadRequest(
            "Only .docx templates can be auto-filled. Replace the template in "
            "Setup → Documentation with a .docx file, then try Fill Word again."
        )
    try:
        fh = doc_item.word_template.open("rb")
    except OSError:
        return HttpResponseBadRequest(
            "The database still points to a Word template, but the file is not on this "
            "server under media/ (for example after the media folder was cleared, the app "
            "was run from a different copy of the project, or the template was never "
            "uploaded in Setup only saved on your PC). Re-upload the .docx in "
            "Setup → Documentation for this standard document."
        )
    try:
        with fh:
            filled = fill_docx_template(
                fh,
                merge_context_for_engagement(
                    engagement, documentation_map=documentation_map
                ),
            )
    except Exception:
        logging.getLogger(__name__).exception(
            "Fill Word failed for engagement_pk=%s map_pk=%s documentation_pk=%s",
            engagement_pk,
            map_pk,
            doc_item.pk,
        )
        return HttpResponseServerError(
            "Fill Word failed while building the document. If this persists, "
            "check server logs or simplify placeholders in the .docx template."
        )
    unresolved = list_unresolved_tokens_in_document_xml(filled)
    if unresolved:
        logging.getLogger(__name__).warning(
            "Filled docx still contains placeholders (split runs or unknown tokens): %s",
            ", ".join(unresolved),
        )
    download_name = filled_engagement_documentation_docx_filename(
        documentation_date=documentation_map.documentation_date,
        fy_no=engagement.fiscal_year.fy_no,
        client_code=engagement.client.client_code,
        service_code=engagement.service.service_code,
        standard_document=doc_item.standard_document,
        filled_download_label=getattr(doc_item, "filled_download_label", "") or "",
    )
    response = FileResponse(
        io.BytesIO(filled),
        as_attachment=True,
        filename=download_name,
        content_type=word_template_content_type(download_name),
    )
    return response


@login_required
@require_GET
def engagement_documentation_attachment_download(
    request, engagement_pk, map_pk, pk
):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    attachment = get_object_or_404(
        EngagementDocumentationMapAttachment.objects.select_related(
            "documentation_map__engagement"
        ),
        pk=pk,
        documentation_map_id=map_pk,
        documentation_map__engagement_id=engagement.pk,
    )
    if not attachment.file:
        raise Http404
    safe_name = get_valid_filename(attachment.original_filename) or "download"
    try:
        file_handle = attachment.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


def _documentation_option_label(item):
    names = ", ".join(
        c.classification_name
        for c in sorted(
            item.applicable_classifications.all(),
            key=lambda c: c.classification_name,
        )
    )
    return f"{item.standard_document} ({item.get_document_stage_display()} - {names})"


@login_required
@require_GET
def engagement_documentation_option_search(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    q = (request.GET.get("q") or "").strip()
    current_id = (request.GET.get("for_user") or "").strip()

    used_ids = EngagementDocumentationMap.objects.filter(
        engagement=engagement
    ).values_list("documentation_id", flat=True)
    if current_id.isdigit():
        used_ids = used_ids.exclude(documentation_id=int(current_id))

    include_pk = int(current_id) if current_id.isdigit() else None
    items = (
        EngagementDocumentation.objects.prefetch_related("applicable_classifications")
        .exclude(pk__in=used_ids)
        .order_by("document_stage", "standard_document")
    )
    items = filter_engagement_documentation_by_client_classification(
        items,
        engagement.client,
        include_documentation_pk=include_pk,
    )
    if q:
        items = items.filter(
            Q(standard_document__icontains=q)
            | Q(document_stage__icontains=q)
            | Q(applicable_classifications__classification_name__icontains=q)
        ).distinct()

    payload = [{"id": item.pk, "label": _documentation_option_label(item)} for item in items[:50]]
    return JsonResponse(payload, safe=False)


def _engagement_documentation_map_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        form = EngagementDocumentationMapForm(
            request.POST,
            instance=instance,
            engagement=engagement,
        )
        if form.is_valid():
            selected_docs = form.cleaned_data.get("documentation")
            if instance is None and hasattr(selected_docs, "__iter__") and not isinstance(selected_docs, EngagementDocumentation):
                existing_ids = set(
                    EngagementDocumentationMap.objects.filter(
                        engagement=engagement
                    ).values_list("documentation_id", flat=True)
                )
                doc_date = form.cleaned_data["documentation_date"]
                new_maps = [
                    EngagementDocumentationMap(
                        engagement=engagement,
                        documentation=doc,
                        documentation_date=doc_date,
                        created_by=request.user,
                    )
                    for doc in selected_docs
                    if doc.pk not in existing_ids
                ]
                if new_maps:
                    with transaction.atomic():
                        EngagementDocumentationMap.objects.bulk_create(new_maps)
            else:
                with transaction.atomic():
                    documentation_map = form.save(commit=False)
                    if instance is None:
                        documentation_map.engagement = engagement
                        documentation_map.created_by = request.user
                    documentation_map.save()
                    if is_mr02_documentation(documentation_map.documentation):
                        documentation_map.representation_point_matrix = (
                            parse_representation_matrix_post(request.POST)
                        )
                    else:
                        documentation_map.representation_point_matrix = {}
                    documentation_map.save(
                        update_fields=["representation_point_matrix"]
                    )
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
    else:
        form = EngagementDocumentationMapForm(instance=instance, engagement=engagement)

    ctx = {
        "form": form,
        "engagement": engagement,
        "documentation_map": instance,
    }
    if instance is not None and instance.documentation_id:
        doc = instance.documentation
        if is_mr02_documentation(doc):
            matrix = instance.representation_point_matrix or {}
            ctx["mr02_status_choices"] = REPRESENTATION_POINT_STATUS_CHOICES
            ctx["mr02_point_rows_ui"] = [
                {
                    "p": p,
                    "status": (matrix.get(p["id"]) or {}).get("status", ""),
                    "notes": (matrix.get(p["id"]) or {}).get("notes", ""),
                }
                for p in mr02_point_rows()
            ]

    return render(
        request,
        "engagements/engagement_documentation_map_form.html",
        ctx,
    )


@login_required
def engagement_documentation_map_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    return _engagement_documentation_map_form_view(request, engagement=engagement)


@login_required
def engagement_documentation_map_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=pk,
        engagement=engagement,
    )
    return _engagement_documentation_map_form_view(
        request,
        engagement=engagement,
        instance=documentation_map,
    )


def _redirect_engagement_divisions_list(request):
    """Preserve ?team=/status from URL, or fall back to last saved filters."""
    base = reverse("engagement_divisions")
    params = request.GET.copy()
    if "team" not in params:
        saved = request.session.get(_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY, "all")
        if saved in _DIVISION_TEAM_LIST_FILTERS and saved != "all":
            params["team"] = saved
    if "status" not in params:
        saved = request.session.get(_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY, "active")
        if saved in _DIVISION_STATUS_LIST_FILTERS and saved != "active":
            params["status"] = saved
    if params:
        return redirect(f"{base}?{params.urlencode()}")
    return redirect(base)


@login_required
def engagement_divisions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            division = get_object_or_404(
                _engagement_division_queryset_for_user(request.user),
                pk=request.POST.get("pk"),
            )
            division.delete()
            return _redirect_engagement_divisions_list(request)
        return _redirect_engagement_divisions_list(request)

    team_param = request.GET.get("team")
    if team_param is not None:
        raw_team = team_param.strip().lower()
        if raw_team not in _DIVISION_TEAM_LIST_FILTERS:
            raw_team = "all"
        request.session[_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY] = raw_team
    else:
        raw_team = request.session.get(_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY, "all")
        if raw_team not in _DIVISION_TEAM_LIST_FILTERS:
            raw_team = "all"

    status_param = request.GET.get("status")
    if status_param is not None:
        raw_status = status_param.strip().lower()
        if raw_status not in _DIVISION_STATUS_LIST_FILTERS:
            raw_status = "active"
        request.session[_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY] = raw_status
    else:
        raw_status = request.session.get(
            _ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY, "active"
        )
        if raw_status not in _DIVISION_STATUS_LIST_FILTERS:
            raw_status = "active"

    divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .annotate(
            division_work_area_count=Count("work_areas", distinct=True),
            documentation_count=Count("documentation_maps", distinct=True),
            team_assignment_count=Count("team_assignments", distinct=True),
            status_remark_count=Count("status_remarks", distinct=True),
        )
    )
    if not request.user.is_superuser:
        divisions = divisions.exclude(engagement__status=STATUS_COMPLETED)
    if raw_status == "active":
        divisions = divisions.exclude(status=STATUS_COMPLETED)
    if raw_team == "unassigned":
        divisions = divisions.filter(team_assignment_count=0)
    divisions = filter_by_engagement_id(divisions, request, "engagement_id")

    return render(
        request,
        "engagements/engagement_divisions.html",
        {
            "divisions": divisions,
            "division_team_filter": raw_team,
            "division_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
        },
    )


@login_required
@require_GET
def engagement_schedule_bounds_json(request, engagement_pk):
    """Min planned start and max planned finish across engagement schedule rows (for division form autofill)."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    assert_engagement_open_for_management(request.user, engagement)
    earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
    return JsonResponse(
        {
            "planned_start": earliest_start.isoformat() if earliest_start else None,
            "planned_finish": latest_finish.isoformat() if latest_finish else None,
        }
    )


def _engagement_division_form_view(request, instance=None):
    if instance is not None:
        assert_division_open_for_management(request.user, instance)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_engagement = instance.engagement if instance is not None else None
        original_division_name = instance.division_name if instance is not None else None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = EngagementDivisionForm(request.POST, instance=instance)
        if form.is_valid():
            if instance is None:
                cand_eng = form.cleaned_data.get("engagement")
                assert_engagement_open_for_management(request.user, cand_eng)
            division = form.save(commit=False)
            if not _can_manage_structure(request.user) and instance is not None:
                division.engagement = original_engagement
                division.division_name = original_division_name
                division.planned_start = original_planned_start
                division.planned_finish = original_planned_finish
            if (
                instance is not None
                and not request.user.is_superuser
                and had_actual_finish
                and division.actual_finish is None
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed division.",
                )
                return redirect("engagement_division_edit", pk=instance.pk)
            if instance is None:
                division.created_by = request.user
            division.save()
            return redirect("engagement_divisions")
    else:
        form = EngagementDivisionForm(instance=instance)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["engagement"].disabled = True
            form.fields["division_name"].disabled = True
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    team_assignments = []
    if instance is not None:
        team_assignments = list(
            instance.team_assignments.select_related("team_member").all()
        )

    return render(
        request,
        "engagements/engagement_division_form.html",
        {
            "form": form,
            "division": instance,
            "team_assignments": team_assignments,
        },
    )


@login_required
def engagement_division_create(request):
    return _engagement_division_form_view(request)


@login_required
def engagement_division_edit(request, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=pk
    )
    return _engagement_division_form_view(request, instance=division)


@login_required
def engagement_division_team_assignments(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            assignment = get_object_or_404(
                EngagementDivisionTeamAssignment,
                pk=request.POST.get("pk"),
                division=division,
            )
            assignment.delete()
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
        if action == "send_assignment_mail":
            assignment = get_object_or_404(
                EngagementDivisionTeamAssignment,
                pk=request.POST.get("pk"),
                division=division,
            )
            team_mail.manual_notify_division_team_assignment(request, assignment)
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
        return redirect("engagement_division_team_assignments", division_pk=division.pk)

    team_assignments = division.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_division_team_assignments.html",
        {
            "division": division,
            "team_assignments": team_assignments,
            "today": timezone.localdate(),
        },
    )


def _engagement_division_team_assignment_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementDivisionTeamAssignmentForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.division = division
                assignment.created_by = request.user
            assignment.save()
            team_mail.maybe_auto_notify_division_team_assignment(request, assignment)
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
    else:
        form = EngagementDivisionTeamAssignmentForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_team_assignment_form.html",
        {
            "form": form,
            "division": division,
            "assignment": instance,
        },
    )


@login_required
def engagement_division_team_assignment_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    return _engagement_division_team_assignment_form_view(request, division=division)


@login_required
def engagement_division_team_assignment_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    assignment = get_object_or_404(
        EngagementDivisionTeamAssignment,
        pk=pk,
        division=division,
    )
    return _engagement_division_team_assignment_form_view(
        request,
        division=division,
        instance=assignment,
    )


@login_required
def engagement_division_documentation_maps(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    eligible_source_divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .exclude(pk=division.pk)
        .filter(
            engagement__client_id=division.engagement.client_id,
            engagement__service_id=division.engagement.service_id,
            engagement__fiscal_year_id=division.engagement.fiscal_year_id,
        )
    )
    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "copy_from_division":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            source_division_id = (request.POST.get("source_division_id") or "").strip()
            if not source_division_id:
                messages.error(request, "Select a source division.")
                return redirect(
                    "engagement_division_documentation_maps",
                    division_pk=division.pk,
                )
            source_division = eligible_source_divisions.filter(pk=source_division_id).first()
            if source_division is None:
                messages.error(
                    request,
                    (
                        "Selected source division is invalid. Choose one with the same "
                        "client, service, and fiscal year."
                    ),
                )
                return redirect(
                    "engagement_division_documentation_maps",
                    division_pk=division.pk,
                )
            with transaction.atomic():
                existing_ids = set(
                    EngagementDivisionDocumentationMap.objects.filter(
                        division=division
                    ).values_list("documentation_id", flat=True)
                )
                source_maps = source_division.documentation_maps.select_related(
                    "documentation"
                ).order_by(
                    "documentation__document_stage",
                    "documentation__standard_document",
                )
                new_maps = [
                    EngagementDivisionDocumentationMap(
                        division=division,
                        documentation=source_map.documentation,
                        created_by=request.user,
                    )
                    for source_map in source_maps
                    if source_map.documentation_id not in existing_ids
                ]
                created_count = len(new_maps)
                if new_maps:
                    EngagementDivisionDocumentationMap.objects.bulk_create(new_maps)
            if created_count:
                messages.success(
                    request,
                    (
                        f"Copied {created_count} documentation mapping(s) from "
                        f"{source_division.division_name}."
                    ),
                )
            else:
                messages.info(
                    request,
                    "No new documentation mappings to copy from the selected division.",
                )
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        if action == "delete":
            documentation_map = get_object_or_404(
                EngagementDivisionDocumentationMap,
                pk=request.POST.get("pk"),
                division=division,
            )
            documentation_map.delete()
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        if action == "delete_all_documentation_maps":
            qs = division.documentation_maps.all()
            n = qs.count()
            if n:
                with transaction.atomic():
                    qs.delete()
                messages.success(
                    request,
                    (
                        f"Removed {n} division documentation mapping(s) "
                        "(including uploaded files under each mapping)."
                    ),
                )
            else:
                messages.info(request, "No division documentation mappings to remove.")
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        return redirect("engagement_division_documentation_maps", division_pk=division.pk)

    documentation_maps = division.documentation_maps.select_related("documentation").annotate(
        attachment_count=Count("attachments", distinct=True)
    )
    source_divisions = eligible_source_divisions.order_by(
        "engagement__client__client_name",
        "-engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "division_name",
    )
    return render(
        request,
        "engagements/engagement_division_documentation_maps.html",
        {
            "division": division,
            "documentation_maps": documentation_maps,
            "source_divisions": source_divisions,
        },
    )


@login_required
def engagement_division_documentation_map_files(request, division_pk, map_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDivisionDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        division=division,
    )
    files_redirect = redirect(
        "engagement_division_documentation_map_files",
        division_pk=division.pk,
        map_pk=documentation_map.pk,
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "upload_attachment":
            files = request.FILES.getlist("files")
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            description = (request.POST.get("description") or "").strip()
            if doc_date is None:
                messages.error(request, "Document date is required.")
                return files_redirect
            if not files:
                messages.warning(request, "No files were selected.")
                return files_redirect
            n = 0
            with transaction.atomic():
                for upload in files[:30]:
                    EngagementDivisionDocumentationMapAttachment.objects.create(
                        documentation_map=documentation_map,
                        file=upload,
                        original_filename=(upload.name or "file")[:255],
                        document_date=doc_date,
                        description=description,
                        created_by=request.user,
                    )
                    n += 1
            messages.success(request, f"Added {n} file(s).")
            return files_redirect
        if action == "delete_attachment":
            attachment = get_object_or_404(
                EngagementDivisionDocumentationMapAttachment,
                pk=request.POST.get("pk"),
                documentation_map=documentation_map,
            )
            attachment.delete()
            messages.success(request, "Attachment removed.")
            return files_redirect
        return files_redirect

    attachments = documentation_map.attachments.order_by(
        "-document_date", "original_filename", "pk"
    )
    return render(
        request,
        "engagements/engagement_division_documentation_map_files.html",
        {
            "division": division,
            "documentation_map": documentation_map,
            "attachments": attachments,
        },
    )


@login_required
@require_GET
def engagement_division_documentation_attachment_download(
    request, division_pk, map_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    attachment = get_object_or_404(
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division"
        ),
        pk=pk,
        documentation_map_id=map_pk,
        documentation_map__division_id=division.pk,
    )
    if not attachment.file:
        raise Http404
    safe_name = get_valid_filename(attachment.original_filename) or "download"
    try:
        file_handle = attachment.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
@require_GET
def engagement_division_documentation_option_search(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    assert_division_open_for_management(request.user, division)
    q = (request.GET.get("q") or "").strip()
    current_id = (request.GET.get("for_user") or "").strip()

    used_ids = EngagementDivisionDocumentationMap.objects.filter(
        division=division
    ).values_list("documentation_id", flat=True)
    if current_id.isdigit():
        used_ids = used_ids.exclude(documentation_id=int(current_id))

    include_pk = int(current_id) if current_id.isdigit() else None
    items = (
        EngagementDocumentation.objects.prefetch_related("applicable_classifications")
        .exclude(pk__in=used_ids)
        .order_by("document_stage", "standard_document")
    )
    items = filter_engagement_documentation_by_client_classification(
        items,
        division.engagement.client,
        include_documentation_pk=include_pk,
    )
    if q:
        items = items.filter(
            Q(standard_document__icontains=q)
            | Q(document_stage__icontains=q)
            | Q(applicable_classifications__classification_name__icontains=q)
        ).distinct()

    payload = [{"id": item.pk, "label": _documentation_option_label(item)} for item in items[:50]]
    return JsonResponse(payload, safe=False)


def _engagement_division_documentation_map_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        form = EngagementDivisionDocumentationMapForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            selected_docs = form.cleaned_data.get("documentation")
            if instance is None and hasattr(selected_docs, "__iter__") and not isinstance(selected_docs, EngagementDocumentation):
                existing_ids = set(
                    EngagementDivisionDocumentationMap.objects.filter(
                        division=division
                    ).values_list("documentation_id", flat=True)
                )
                new_maps = [
                    EngagementDivisionDocumentationMap(
                        division=division,
                        documentation=doc,
                        created_by=request.user,
                    )
                    for doc in selected_docs
                    if doc.pk not in existing_ids
                ]
                if new_maps:
                    with transaction.atomic():
                        EngagementDivisionDocumentationMap.objects.bulk_create(new_maps)
            else:
                with transaction.atomic():
                    documentation_map = form.save(commit=False)
                    if instance is None:
                        documentation_map.division = division
                        documentation_map.created_by = request.user
                    documentation_map.save()
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
    else:
        form = EngagementDivisionDocumentationMapForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_documentation_map_form.html",
        {
            "form": form,
            "division": division,
            "documentation_map": instance,
            "add_documentation_url": reverse("engagement_documentation_create")
            + "?"
            + urlencode({"next": request.get_full_path()}),
        },
    )


@login_required
def engagement_division_documentation_map_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    return _engagement_division_documentation_map_form_view(request, division=division)


@login_required
def engagement_division_documentation_map_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDivisionDocumentationMap,
        pk=pk,
        division=division,
    )
    return _engagement_division_documentation_map_form_view(
        request,
        division=division,
        instance=documentation_map,
    )


