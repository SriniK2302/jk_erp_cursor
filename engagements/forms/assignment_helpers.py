from datetime import timedelta

from django.db.models import Min

from hr.teams.models import TeamMember, TeamMemberGradePeriod, TeamMemberRollPeriod

from engagements.models import (
    EngagementDivisionTeamAssignment,
    EngagementTeamAssignment,
)

def _team_member_pks_assigned_to_engagement_division(division):
    if division is None:
        return set()
    return set(
        EngagementDivisionTeamAssignment.objects.filter(
            division=division,
        ).values_list("team_member_id", flat=True)
    )


def _team_member_pks_assigned_to_engagement(engagement):
    if engagement is None:
        return set()
    return set(
        EngagementTeamAssignment.objects.filter(
            engagement=engagement,
        ).values_list("team_member_id", flat=True)
    )


def _work_area_team_member_queryset_allowed_pks(allowed_ids, instance):
    pks = set(allowed_ids)
    if (
        instance
        and getattr(instance, "pk", None)
        and getattr(instance, "team_member_id", None)
    ):
        pks.add(instance.team_member_id)
    return (
        TeamMember.objects.filter(pk__in=pks).order_by("first_name", "last_name", "code")
        if pks
        else TeamMember.objects.none()
    )


def _team_member_earliest_roll_start_map(team_member_ids):
    rows = (
        TeamMemberRollPeriod.objects.filter(team_member_id__in=team_member_ids)
        .values("team_member_id")
        .annotate(earliest_from=Min("from_date"))
    )
    return {
        str(row["team_member_id"]): row["earliest_from"].isoformat()
        for row in rows
        if row["earliest_from"] is not None
    }


def _format_member_period_hints(periods_qs) -> str:
    parts = []
    for period in periods_qs.order_by("from_date", "id"):
        end_label = period.to_date.isoformat() if period.to_date else "Present"
        parts.append(f"{period.from_date.isoformat()} to {end_label}")
    return "; ".join(parts)


def _assignment_period_source(team_member):
    grade_qs = TeamMemberGradePeriod.objects.filter(team_member=team_member)
    if grade_qs.exists():
        return grade_qs, "role", "grade mapping"
    roll_qs = TeamMemberRollPeriod.objects.filter(team_member=team_member)
    return roll_qs, "on-roll", "roll"


def _date_range_fully_covered_by_periods(periods_qs, range_start, range_end) -> bool:
    periods = list(periods_qs.order_by("from_date", "id"))
    if not periods:
        return False

    cursor = range_start
    while cursor <= range_end:
        matched = None
        for period in periods:
            period_end = period.to_date
            if period.from_date <= cursor and (
                period_end is None or period_end >= cursor
            ):
                matched = period
                break
        if matched is None:
            return False
        segment_end = matched.to_date or range_end
        segment_end = min(segment_end, range_end)
        cursor = segment_end + timedelta(days=1)
    return True


def _team_member_planned_dates_within_assignment_periods(
    team_member, planned_start, planned_finish
) -> bool:
    if team_member is None or planned_start is None or planned_finish is None:
        return False
    periods_qs, _, _ = _assignment_period_source(team_member)
    return _date_range_fully_covered_by_periods(
        periods_qs, planned_start, planned_finish
    )


def _assignment_period_validation_error(team_member):
    periods_qs, period_kind, period_label = _assignment_period_source(team_member)
    if not periods_qs.exists():
        setup_hint = (
            "Add team grade mappings first."
            if period_label == "grade mapping"
            else "Add team roll dates first."
        )
        return (
            "team_member",
            f"Selected team member has no team {period_label} period. {setup_hint}",
        )
    return (
        "planned_start",
        (
            f"Assignment dates must fall within {period_kind} period(s) for this member "
            "(each day in the range must be covered). "
            f"Recorded periods: {_format_member_period_hints(periods_qs)}."
        ),
    )

