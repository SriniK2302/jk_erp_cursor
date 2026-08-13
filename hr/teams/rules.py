from __future__ import annotations

from datetime import timedelta


def get_subsequent_grade_period(team_member, from_date, *, exclude_period_id=None):
    qs = team_member.grade_periods.filter(from_date__gt=from_date)
    if exclude_period_id is not None:
        qs = qs.exclude(pk=exclude_period_id)
    return qs.order_by("from_date", "id").first()


def is_grade_period_to_date_locked(period) -> bool:
    if period is None or not period.pk:
        return False
    return (
        get_subsequent_grade_period(
            period.team_member,
            period.from_date,
            exclude_period_id=period.pk,
        )
        is not None
    )


def locked_grade_period_to_date(period):
    next_period = get_subsequent_grade_period(
        period.team_member,
        period.from_date,
        exclude_period_id=period.pk,
    )
    if next_period is None:
        return None
    return next_period.from_date - timedelta(days=1)


def get_team_grade_mapping_defaults(team_member, *, period=None, exclude_period_id=None):
    roll_period = team_member.roll_periods.order_by("-from_date", "-id").first()
    if roll_period is None:
        return {
            "has_roll_period": False,
            "from_date": None,
            "to_date": None,
            "is_to_date_locked": False,
        }

    grade_periods = team_member.grade_periods
    if exclude_period_id is not None:
        grade_periods = grade_periods.exclude(pk=exclude_period_id)

    latest_closed_grade = grade_periods.exclude(to_date__isnull=True).order_by(
        "-to_date",
        "-id",
    ).first()
    start_date = roll_period.from_date
    if latest_closed_grade is not None:
        start_date = max(start_date, latest_closed_grade.to_date + timedelta(days=1))

    is_to_date_locked = is_grade_period_to_date_locked(period)
    if is_to_date_locked:
        suggested_to_date = locked_grade_period_to_date(period)
    else:
        suggested_to_date = roll_period.to_date

    return {
        "has_roll_period": True,
        "from_date": start_date,
        "to_date": suggested_to_date,
        "is_to_date_locked": is_to_date_locked,
    }
