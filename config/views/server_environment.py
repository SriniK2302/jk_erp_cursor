from django.conf import settings
from django.contrib import messages

from config.server_access import can_manage_server_environment
from config.trial_database import (
    copy_user_from_live,
    migration_status,
    provision_trial_database,
    run_migrations,
    trial_database_name,
    trial_user_exists,
)
from config.views._std_imports import *  # noqa: F403


def _redirect_with_output(request, output: str, success_message: str):
    request.session['server_environment_output'] = output
    messages.success(request, success_message)
    return redirect('setup_server_environment')


def _redirect_with_error(request, message: str):
    messages.error(request, message)
    return redirect('setup_server_environment')


@login_required
def setup_server_environment(request):
    if not can_manage_server_environment(request.user):
        raise PermissionDenied('Only the authorized trial user can manage servers.')

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if not settings.JK_ERP_IS_TRIAL:
            return _redirect_with_error(
                request,
                'Trial database actions are only available on the trial server.',
            )

        if action == 'create_db':
            try:
                output = provision_trial_database()
            except Exception as exc:
                return _redirect_with_error(request, f'Trial database setup failed: {exc}')
            return _redirect_with_output(
                request,
                output,
                'Trial database is ready.',
            )

        if action == 'migrate':
            status = migration_status()
            if not status['trial_db_ready']:
                return _redirect_with_error(
                    request,
                    'Create the trial database before running migrations.',
                )
            try:
                output = run_migrations()
            except Exception as exc:
                return _redirect_with_error(request, f'Migration failed: {exc}')
            return _redirect_with_output(
                request,
                output,
                'Database migrations completed.',
            )

        if action == 'copy_user':
            status = migration_status()
            if not status['trial_db_ready']:
                return _redirect_with_error(
                    request,
                    'Create the trial database before copying the live user.',
                )
            try:
                message = copy_user_from_live(settings.TRIAL_ALLOWED_USERNAME)
            except Exception as exc:
                return _redirect_with_error(request, str(exc))
            return _redirect_with_output(
                request,
                message,
                message,
            )

    operation_output = request.session.pop('server_environment_output', '')
    status = migration_status()
    return render(
        request,
        'setup/server_environment.html',
        {
            'live_server_url': settings.LIVE_SERVER_URL,
            'trial_server_url': settings.TRIAL_SERVER_URL,
            'trial_allowed_username': settings.TRIAL_ALLOWED_USERNAME,
            'trial_database_name': trial_database_name(),
            'trial_user_exists': trial_user_exists(settings.TRIAL_ALLOWED_USERNAME),
            'operation_output': operation_output,
            **status,
        },
    )
