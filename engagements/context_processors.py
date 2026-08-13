from django.db.utils import OperationalError, ProgrammingError

from .session_context import get_session_engagement, session_engagement_choices
from .timesheets.models import TimeSession

_MODULE_ENGAGEMENTS = "module_engagements"


def active_time_session(request):
    ctx = {
        "active_time_session": None,
        "can_use_engagements_nav": False,
        "recent_timer_tasks": [],
        "session_engagement": None,
        "session_engagement_choices": [],
    }
    if not request.user.is_authenticated:
        return ctx
    ctx["can_use_engagements_nav"] = (
        request.user.is_superuser
        or request.user.groups.filter(name=_MODULE_ENGAGEMENTS).exists()
    )
    if ctx["can_use_engagements_nav"]:
        ctx["session_engagement"] = get_session_engagement(request)
        ctx["session_engagement_choices"] = session_engagement_choices(request.user)
    try:
        session = (
            TimeSession.objects.filter(started_by=request.user, ended_at__isnull=True)
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
        ctx["active_time_session"] = session
    except (OperationalError, ProgrammingError):
        pass
    return ctx
