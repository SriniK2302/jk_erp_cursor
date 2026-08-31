"""Template context processors for config."""

from django.conf import settings

from config.server_access import can_manage_server_environment


def server_environment(request):
    user = getattr(request, 'user', None)
    return {
        'jk_erp_env': settings.JK_ERP_ENV,
        'jk_erp_is_trial': settings.JK_ERP_IS_TRIAL,
        'trial_allowed_username': (
            settings.TRIAL_ALLOWED_USERNAME if settings.JK_ERP_IS_TRIAL else ''
        ),
        'live_server_url': settings.LIVE_SERVER_URL,
        'trial_server_url': settings.TRIAL_SERVER_URL,
        'can_manage_server_environment': can_manage_server_environment(user),
    }
