from engagements.views._std_imports import *  # noqa: F403

from .constants import ENGAGEMENTS_MODULE_GROUP

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
