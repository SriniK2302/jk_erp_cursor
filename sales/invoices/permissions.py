from django.core.exceptions import PermissionDenied

_MODULE_SETUP = "module_setup"


def require_setup_module(request) -> None:
    user = request.user
    if user.is_superuser:
        return
    if not user.groups.filter(name=_MODULE_SETUP).exists():
        raise PermissionDenied("You need Setup access to manage invoices.")
