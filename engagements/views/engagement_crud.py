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

