from __future__ import annotations

SESSION_ENGAGEMENT_KEY = "session_engagement_id"


def _engagement_queryset_for_user(user):
    from engagements.views import _engagement_queryset_for_user

    return _engagement_queryset_for_user(user)


def engagement_select_label(engagement) -> str:
    from engagements.forms import _engagement_select_label

    return _engagement_select_label(engagement)


def get_session_engagement_id(request) -> int | None:
    raw = request.session.get(SESSION_ENGAGEMENT_KEY)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_session_engagement(request, user=None):
    """Return the session engagement if set and still accessible; else None."""
    if user is None:
        user = request.user
    pk = get_session_engagement_id(request)
    if pk is None:
        return None
    engagement = (
        _engagement_queryset_for_user(user)
        .filter(pk=pk)
        .select_related("client", "fiscal_year", "service")
        .first()
    )
    if engagement is None:
        request.session.pop(SESSION_ENGAGEMENT_KEY, None)
    return engagement


def set_session_engagement(request, engagement) -> None:
    request.session[SESSION_ENGAGEMENT_KEY] = engagement.pk


def clear_session_engagement(request) -> None:
    request.session.pop(SESSION_ENGAGEMENT_KEY, None)


def engagement_ids_for_lists(user, request) -> list[int]:
    all_ids = list(_engagement_queryset_for_user(user).values_list("pk", flat=True))
    session = get_session_engagement(request, user)
    if session is None:
        return all_ids
    return [session.pk] if session.pk in all_ids else []


def filter_engagement_queryset(qs, request, user=None):
    session = get_session_engagement(request, user)
    if session is None:
        return qs
    return qs.filter(pk=session.pk)


def filter_by_engagement_id(qs, request, field_name: str, user=None):
    session = get_session_engagement(request, user)
    if session is None:
        return qs
    return qs.filter(**{field_name: session.pk})


def session_engagement_choices(user):
    return (
        _engagement_queryset_for_user(user)
        .select_related("client", "fiscal_year", "service")
        .order_by("client__client_name", "fiscal_year__fy_no", "service__service_desc")
    )
