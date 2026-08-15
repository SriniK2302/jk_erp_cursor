from django.db.models import Max, Min

def _engagement_schedule_bounds(engagement):
    window = engagement.schedules.aggregate(
        earliest_start=Min("planned_start"),
        latest_finish=Max("planned_finish"),
    )
    return window["earliest_start"], window["latest_finish"]


def _team_assignment_range_overlaps_qs(qs, *, planned_start, planned_finish):
    """Inclusive dates: overlap if the ranges share at least one day."""
    return qs.filter(
        planned_start__lte=planned_finish,
        planned_finish__gte=planned_start,
    )


def _apply_work_area_schedule_window_errors(
    form,
    cleaned_data,
    *,
    engagement,
    division=None,
):
    planned_start = cleaned_data.get("planned_start")
    planned_finish = cleaned_data.get("planned_finish")
    actual_start = cleaned_data.get("actual_start")
    actual_finish = cleaned_data.get("actual_finish")

    if planned_start and planned_finish and planned_finish < planned_start:
        form.add_error(
            "planned_finish",
            "Planned finish cannot be before planned start.",
        )

    if actual_start and actual_finish and actual_finish < actual_start:
        form.add_error(
            "actual_finish",
            "Actual finish cannot be before actual start.",
        )

    if not planned_start or not planned_finish or engagement is None:
        return

    earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
    if earliest_start is None or latest_finish is None:
        # No engagement-level plan exists yet. Allow work-area save and let
        # the view layer optionally backfill engagement schedule from this row.
        return

    if planned_start < earliest_start:
        form.add_error(
            "planned_start",
            (
                "Planned start cannot be earlier than engagement planned start "
                f"({earliest_start.isoformat()})."
            ),
        )
    if planned_finish > latest_finish:
        form.add_error(
            "planned_finish",
            (
                "Planned finish cannot be later than engagement planned finish "
                f"({latest_finish.isoformat()})."
            ),
        )

    if division is not None:
        if (
            division.planned_start is not None
            and planned_start < division.planned_start
        ):
            form.add_error(
                "planned_start",
                (
                    "Planned start cannot be earlier than division planned start "
                    f"({division.planned_start.isoformat()})."
                ),
            )
        if (
            division.planned_finish is not None
            and planned_finish > division.planned_finish
        ):
            form.add_error(
                "planned_finish",
                (
                    "Planned finish cannot be later than division planned finish "
                    f"({division.planned_finish.isoformat()})."
                ),
            )
