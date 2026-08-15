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

def _session_engagement_next_url(request):
    nxt = (request.POST.get("next") or "").strip()
    fallback = reverse("manage_engagements")
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return nxt
    return fallback


@login_required
@require_POST
def session_engagement_set(request):
    next_url = _session_engagement_next_url(request)
    raw_id = (request.POST.get("engagement_id") or "").strip()
    if not raw_id:
        clear_session_engagement(request)
        messages.info(request, "Working engagement cleared.")
        return redirect(next_url)
    if not raw_id.isdigit():
        messages.error(request, "Invalid engagement selection.")
        return redirect(next_url)
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=int(raw_id),
    )
    set_session_engagement(request, engagement)
    messages.success(
        request,
        f"Working engagement set to {engagement_select_label(engagement)}.",
    )
    return redirect(next_url)


@login_required
@require_POST
def session_engagement_clear(request):
    clear_session_engagement(request)
    messages.info(request, "Working engagement cleared.")
    return redirect(_session_engagement_next_url(request))

