"""Closed engagement / division rules for management screens."""

from django.core.exceptions import PermissionDenied

from .models import STATUS_COMPLETED

_MSG_ENGAGEMENT_CLOSED = (
    "This engagement is closed and is no longer available for management."
)
_MSG_DIVISION_CLOSED = (
    "This engagement division is closed and is no longer available for management."
)


def assert_engagement_open_for_management(user, engagement) -> None:
    """Block non-superusers when the engagement is completed (closed)."""
    if user.is_superuser:
        return
    if engagement is not None and engagement.status == STATUS_COMPLETED:
        raise PermissionDenied(_MSG_ENGAGEMENT_CLOSED)


def assert_division_open_for_management(user, division) -> None:
    """Block non-superusers when the engagement or division is completed (closed)."""
    if user.is_superuser:
        return
    if division is None:
        return
    assert_engagement_open_for_management(user, division.engagement)
    if division.status == STATUS_COMPLETED:
        raise PermissionDenied(_MSG_DIVISION_CLOSED)
