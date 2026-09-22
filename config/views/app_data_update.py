from config.views._std_imports import *  # noqa: F403

from config.app_data_update_registry import list_fields, list_tables, run_update


def _require_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Admin only.")


@login_required
def app_data_update(request):
    _require_superuser(request)
    return render(request, "app_data_update.html", {})


@login_required
@require_GET
def app_data_update_tables_json(request):
    _require_superuser(request)
    search = request.GET.get("q", "")
    return JsonResponse({"tables": list_tables(search)})


@login_required
@require_GET
def app_data_update_fields_json(request):
    _require_superuser(request)
    table_key = request.GET.get("table", "")
    if not table_key:
        return JsonResponse({"fields": []})
    return JsonResponse({"fields": list_fields(table_key)})


@login_required
@require_POST
def app_data_update_run(request):
    _require_superuser(request)
    table_key = request.POST.get("table", "")
    field_name = request.POST.get("field", "")
    old_value = request.POST.get("old_value", "")
    new_value = request.POST.get("new_value", "")
    try:
        summary = run_update(table_key, field_name, old_value, new_value)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": f"Update failed: {exc}"}, status=400)
    return JsonResponse({"ok": True, "message": summary})
