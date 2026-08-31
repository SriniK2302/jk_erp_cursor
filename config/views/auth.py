"""Authentication views."""

from django.conf import settings
from django.contrib.auth.views import LoginView


class TrialRestrictedLoginView(LoginView):
    """Reject login on the trial server for users other than TRIAL_ALLOWED_USERNAME."""

    redirect_authenticated_user = True

    def form_valid(self, form):
        if settings.JK_ERP_IS_TRIAL:
            username = form.cleaned_data.get('username', '').strip().lower()
            if username != settings.TRIAL_ALLOWED_USERNAME:
                form.add_error(
                    None,
                    'This trial server is only available to authorized users.',
                )
                return self.form_invalid(form)
        return super().form_valid(form)
