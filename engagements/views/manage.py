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
def manage_engagements(request):
    return render(
        request,
        "engagements/manage_engagements.html",
        {"can_manage_structure": _can_manage_structure(request.user)},
    )


