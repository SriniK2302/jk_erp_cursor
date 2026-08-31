"""Project middleware."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class TrialServerAccessMiddleware:
    """On the trial server, only the configured username may stay logged in."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.JK_ERP_IS_TRIAL:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                allowed = settings.TRIAL_ALLOWED_USERNAME
                if user.username.lower() != allowed:
                    logout(request)
                    messages.error(
                        request,
                        f'This trial server is restricted to user "{allowed}".',
                    )
                    return redirect(settings.LOGIN_URL)
        return self.get_response(request)
