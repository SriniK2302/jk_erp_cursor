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

