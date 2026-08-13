from .context import clear_audit_user, set_audit_user


class AuditUserMiddleware:
    """Binds the current request user for audit signal handlers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_audit_user(request.user if request.user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            clear_audit_user()
