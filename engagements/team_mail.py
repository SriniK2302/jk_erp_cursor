"""Team assignment notification emails (Zoho / SMTP via SmtpMailSettings)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Literal

from django.core.mail import get_connection, send_mail
from django.http import HttpRequest
from django.utils import timezone

from .models import (
    DivisionWorkAreaConfirmationMailLog,
    DivisionWorkAreaTeamAssignment,
    EngagementDivision,
    EngagementDivisionTeamAssignment,
    EngagementTeamAssignment,
)

logger = logging.getLogger(__name__)


def _smtp_settings_ready() -> bool:
    from config.models import SmtpMailSettings

    s = SmtpMailSettings.get_solo()
    if not s.enabled:
        return False
    if not (s.username and s.password and s.default_from_email):
        return False
    if s.use_tls and s.use_ssl:
        return False
    return True


def _get_connection():
    from config.models import SmtpMailSettings

    s = SmtpMailSettings.get_solo()
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=s.smtp_host,
        port=s.smtp_port,
        username=s.username,
        password=s.password,
        use_tls=s.use_tls,
        use_ssl=s.use_ssl,
    )


def _from_email() -> str:
    from config.models import SmtpMailSettings

    return SmtpMailSettings.get_solo().default_from_email.strip()


def send_engagement_team_assignment_email(
    assignment: EngagementTeamAssignment,
) -> tuple[bool, str | None]:
    """Send one assignment email. Does not update notified_at."""
    from config.models import SmtpMailSettings

    if not _smtp_settings_ready():
        s = SmtpMailSettings.get_solo()
        if not s.enabled:
            return False, "Mail is disabled in Setup → Mail (Zoho SMTP)."
        return False, "Complete SMTP settings (username, password, from email) in Setup → Mail."

    recipient = (assignment.team_member.work_email or "").strip()
    if not recipient:
        return False, "Team member has no work email; add one on Teams."

    e = assignment.engagement
    tm = assignment.team_member
    subject = f"Engagement assignment: {e.client.display_name} ({e.fiscal_year.fy_no})"
    body = (
        f"Dear {tm.first_name} {tm.last_name},\n\n"
        f"You have been assigned to this engagement:\n\n"
        f"Client: {e.client.display_name}\n"
        f"Fiscal year: {e.fiscal_year.fy_no}\n"
        f"Service: {e.service.service_desc}\n"
        f"Planned period: {assignment.planned_start.isoformat()} to {assignment.planned_finish.isoformat()}\n\n"
        f"This message was sent from JK ERP.\n"
    )
    try:
        send_mail(
            subject,
            body,
            _from_email(),
            [recipient],
            connection=_get_connection(),
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("SMTP send failed for engagement team assignment %s", assignment.pk)
        return False, f"Could not send email: {exc}"

    return True, None


def send_division_team_assignment_email(
    assignment: EngagementDivisionTeamAssignment,
) -> tuple[bool, str | None]:
    from config.models import SmtpMailSettings

    if not _smtp_settings_ready():
        s = SmtpMailSettings.get_solo()
        if not s.enabled:
            return False, "Mail is disabled in Setup → Mail (Zoho SMTP)."
        return False, "Complete SMTP settings (username, password, from email) in Setup → Mail."

    recipient = (assignment.team_member.work_email or "").strip()
    if not recipient:
        return False, "Team member has no work email; add one on Teams."

    div = assignment.division
    e = div.engagement
    tm = assignment.team_member
    subject = (
        f"Division assignment: {e.client.display_name} ({e.fiscal_year.fy_no}) — {div.division_name}"
    )
    body = (
        f"Dear {tm.first_name} {tm.last_name},\n\n"
        f"You have been assigned to this engagement division:\n\n"
        f"Client: {e.client.display_name}\n"
        f"Fiscal year: {e.fiscal_year.fy_no}\n"
        f"Service: {e.service.service_desc}\n"
        f"Division: {div.division_name}\n"
        f"Planned period: {assignment.planned_start.isoformat()} to {assignment.planned_finish.isoformat()}\n\n"
        f"This message was sent from JK ERP.\n"
    )
    try:
        send_mail(
            subject,
            body,
            _from_email(),
            [recipient],
            connection=_get_connection(),
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("SMTP send failed for division team assignment %s", assignment.pk)
        return False, f"Could not send email: {exc}"

    return True, None


def _assignment_scope_today_or_future(planned_start) -> bool:
    return planned_start >= timezone.localdate()


def maybe_auto_notify_engagement_team_assignment(
    request: HttpRequest,
    assignment: EngagementTeamAssignment,
) -> None:
    from django.contrib import messages

    if assignment.notified_at:
        return
    if not _assignment_scope_today_or_future(assignment.planned_start):
        return
    if not (assignment.team_member.work_email or "").strip():
        messages.warning(
            request,
            "No work email on file for this team member; assignment was saved but no mail was sent.",
        )
        return
    ok, err = send_engagement_team_assignment_email(assignment)
    if ok:
        assignment.notified_at = timezone.now()
        assignment.save(update_fields=["notified_at"])
        messages.success(
            request,
            f"Assignment notification sent to {assignment.team_member.work_email}.",
        )
    elif err:
        messages.warning(request, err)


def maybe_auto_notify_division_team_assignment(
    request: HttpRequest,
    assignment: EngagementDivisionTeamAssignment,
) -> None:
    from django.contrib import messages

    if assignment.notified_at:
        return
    if not _assignment_scope_today_or_future(assignment.planned_start):
        return
    if not (assignment.team_member.work_email or "").strip():
        messages.warning(
            request,
            "No work email on file for this team member; assignment was saved but no mail was sent.",
        )
        return
    ok, err = send_division_team_assignment_email(assignment)
    if ok:
        assignment.notified_at = timezone.now()
        assignment.save(update_fields=["notified_at"])
        messages.success(
            request,
            f"Assignment notification sent to {assignment.team_member.work_email}.",
        )
    elif err:
        messages.warning(request, err)


def manual_notify_engagement_team_assignment(
    request: HttpRequest,
    assignment: EngagementTeamAssignment,
) -> Literal["ok", "error"]:
    from django.contrib import messages

    ok, err = send_engagement_team_assignment_email(assignment)
    if ok:
        assignment.notified_at = timezone.now()
        assignment.save(update_fields=["notified_at"])
        messages.success(request, "Confirmation mail sent.")
        return "ok"
    if err:
        messages.error(request, err)
    return "error"


def manual_notify_division_team_assignment(
    request: HttpRequest,
    assignment: EngagementDivisionTeamAssignment,
) -> Literal["ok", "error"]:
    from django.contrib import messages

    ok, err = send_division_team_assignment_email(assignment)
    if ok:
        assignment.notified_at = timezone.now()
        assignment.save(update_fields=["notified_at"])
        messages.success(request, "Confirmation mail sent.")
        return "ok"
    if err:
        messages.error(request, err)
    return "error"


def _build_division_work_area_confirmation_mail(
    *, division: EngagementDivision, team_member, assignments
) -> tuple[str, str]:
    engagement = division.engagement
    subject = (
        "Work area assignment confirmation: "
        f"{engagement.client.display_name} ({engagement.fiscal_year.fy_no}) — {division.division_name}"
    )
    lines = [
        f"Dear {team_member.first_name} {team_member.last_name},",
        "",
        "This is a confirmation mail for your current work area assignment(s).",
        "For future notifications, wording may differ as per policy.",
        "",
        "Client: " + engagement.client.display_name,
        "Fiscal year: " + engagement.fiscal_year.fy_no,
        "Service: " + engagement.service.service_desc,
        "Division: " + division.division_name,
        "",
        "Assignments:",
    ]
    for idx, assignment in enumerate(assignments, start=1):
        start = assignment.planned_start.isoformat() if assignment.planned_start else "—"
        finish = assignment.planned_finish.isoformat() if assignment.planned_finish else "—"
        lines.append(
            f"{idx}. {assignment.work_area.work_area_name} — Planned: {start} to {finish}"
        )
    lines.extend(
        [
            "",
            "Please review and contact your reporting manager if any correction is needed.",
            "",
            "Regards,",
            "JK ERP",
        ]
    )
    return subject, "\n".join(lines)


def manual_notify_division_work_area_confirmation_mail(
    request: HttpRequest,
    division: EngagementDivision,
) -> Literal["sent", "noop", "error"]:
    return _manual_notify_division_work_area_confirmation_mail_impl(
        request,
        division,
        force_resend=False,
        quiet=False,
    )


def manual_notify_division_work_area_confirmation_mail_repeat(
    request: HttpRequest,
    division: EngagementDivision,
) -> Literal["sent", "noop", "error"]:
    return _manual_notify_division_work_area_confirmation_mail_impl(
        request,
        division,
        force_resend=True,
        quiet=False,
    )


def silent_notify_division_work_area_confirmation_mail(
    request: HttpRequest,
    division: EngagementDivision,
) -> Literal["sent", "noop", "error"]:
    return _manual_notify_division_work_area_confirmation_mail_impl(
        request,
        division,
        force_resend=False,
        quiet=True,
    )


def _manual_notify_division_work_area_confirmation_mail_impl(
    request: HttpRequest,
    division: EngagementDivision,
    *,
    force_resend: bool,
    quiet: bool,
) -> Literal["sent", "noop", "error"]:
    from django.contrib import messages

    if not _smtp_settings_ready():
        from config.models import SmtpMailSettings

        s = SmtpMailSettings.get_solo()
        if not quiet:
            if not s.enabled:
                messages.error(request, "Mail is disabled in Setup → Mail (Zoho SMTP).")
            else:
                messages.error(
                    request,
                    "Complete SMTP settings (username, password, from email) in Setup → Mail.",
                )
        return "error"

    assignments = list(
        DivisionWorkAreaTeamAssignment.objects.filter(work_area__division=division)
        .select_related(
            "work_area",
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
            "team_member",
        )
        .order_by("team_member__first_name", "team_member__last_name", "work_area__work_area_name", "id")
    )
    if not assignments:
        if not quiet:
            messages.info(request, "No work area team assignments available to notify.")
        return "noop"

    sent_logs = set(
        DivisionWorkAreaConfirmationMailLog.objects.filter(
            assignment_id__in=[a.pk for a in assignments],
            mail_type="confirmation",
        ).values_list("assignment_id", flat=True)
    )
    pending = assignments if force_resend else [a for a in assignments if a.pk not in sent_logs]
    if not pending:
        if not quiet:
            messages.info(
                request,
                "Confirmation mail already sent for all assigned work areas.",
            )
        return "noop"

    grouped = defaultdict(list)
    for assignment in pending:
        grouped[assignment.team_member_id].append(assignment)

    sent_members = 0
    sent_items = 0
    skipped_no_email = 0
    failed_members = 0

    for member_assignments in grouped.values():
        team_member = member_assignments[0].team_member
        recipient = (team_member.work_email or "").strip()
        if not recipient:
            skipped_no_email += 1
            continue

        subject, body = _build_division_work_area_confirmation_mail(
            division=division,
            team_member=team_member,
            assignments=member_assignments,
        )
        try:
            send_mail(
                subject,
                body,
                _from_email(),
                [recipient],
                connection=_get_connection(),
                fail_silently=False,
            )
        except Exception as exc:
            failed_members += 1
            logger.exception(
                "SMTP send failed for division work area confirmation division=%s member=%s",
                division.pk,
                team_member.pk,
            )
            if not quiet:
                messages.error(
                    request,
                    f"Could not send confirmation to {team_member}: {exc}",
                )
            continue

        sent_members += 1
        sent_items += len(member_assignments)
        DivisionWorkAreaConfirmationMailLog.objects.bulk_create(
            [
                DivisionWorkAreaConfirmationMailLog(
                    assignment=assignment,
                    mail_type="confirmation",
                    recipient_email=recipient,
                    subject=subject[:255],
                    sent_by=request.user,
                )
                for assignment in member_assignments
            ],
            ignore_conflicts=True,
        )

    if not quiet:
        if sent_members:
            verb = "resent" if force_resend else "sent"
            messages.success(
                request,
                (
                    f"Confirmation mail {verb} to {sent_members} member(s) "
                    f"for {sent_items} work area assignment(s)."
                ),
            )
        if skipped_no_email:
            messages.warning(
                request,
                f"Skipped {skipped_no_email} member(s) with no work email.",
            )
    if failed_members and not sent_members:
        return "error"
    if sent_members:
        return "sent"
    return "noop"
