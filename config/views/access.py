from config.views._std_imports import *  # noqa: F403

from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS

def _has_module_access(user, module_group_name: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=module_group_name).exists()


def _engagement_queryset_for_user(user):
    qs = Engagement.objects.all()
    if user.is_superuser:
        return qs
    if not _has_module_access(user, MODULE_ENGAGEMENTS):
        return qs.none()
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(divisions__team_assignments__team_member_id__in=team_member)
        | Q(work_areas__team_assignments__team_member_id__in=team_member)
    ).distinct()

