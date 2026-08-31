"""Who may switch servers and run trial database maintenance."""

from django.conf import settings


def can_manage_server_environment(user) -> bool:
    return (
        user.is_authenticated
        and user.username.lower() == settings.TRIAL_ALLOWED_USERNAME
    )
