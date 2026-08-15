from config.views._std_imports import *  # noqa: F403

from .access import _has_module_access
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS
from .home_helpers import _home_work_list_rows

def home(request):
    context = {}
    if request.user.is_authenticated:
        can_engagements = _has_module_access(request.user, MODULE_ENGAGEMENTS)
        can_setup = _has_module_access(request.user, MODULE_SETUP)
        can_tools = _has_module_access(request.user, MODULE_TOOLS)
        context["can_use_engagements"] = can_engagements
        context["can_use_setup"] = can_setup
        context["can_use_tools"] = can_tools
        if can_engagements:
            from engagements.views import (
                _active_time_session_for_user,
                _timer_scope_dict,
            )

            context["active_timer_scope"] = _timer_scope_dict(
                _active_time_session_for_user(request.user)
            )
            context["home_work_list_rows"] = _home_work_list_rows(
                request.user, request=request
            )
    return render(request, "home.html", context)


@login_required
def admin_technical_data_flow(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Only admins can view this document.")
    doc_path = Path(settings.BASE_DIR) / "TECHNICAL_DATA_FLOW.md"
    try:
        doc_text = doc_path.read_text(encoding="utf-8")
    except OSError:
        doc_text = "TECHNICAL_DATA_FLOW.md was not found."
    return render(
        request,
        "admin/technical_data_flow.html",
        {"doc_text": doc_text, "doc_path": doc_path.name},
    )


@login_required
def setup(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    return render(request, "setup.html")


