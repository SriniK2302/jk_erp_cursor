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

