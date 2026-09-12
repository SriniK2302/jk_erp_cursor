from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from config.views.constants import MODULE_TOOLS
from config.views.access import _has_module_access


@login_required
def gmail_process(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")

    from utilities.gmail_accounts_store import load_accounts
    from gmails.gmail_manager import load_search_preferences

    accounts = [a for a in load_accounts() if a.get("token_path")]
    context = {"accounts": accounts}
    context.update(load_search_preferences(request.session))
    return render(request, "gmail_process.html", context)



@login_required
@require_GET
def gmail_process_search_json(request):
    email = (request.GET.get("email") or "").strip()
    label_id = (request.GET.get("label_id") or "").strip()
    scope = (request.GET.get("scope") or "subject").strip()
    keywords = (request.GET.get("keywords") or "").strip()
    target_label_name = (request.GET.get("target_label_name") or "").strip()
    has_attachment = (request.GET.get("has_attachment") or "") == "1"

    from gmails.gmail_manager import save_search_preferences

    save_search_preferences(
        request.session,
        email=email,
        label_id=label_id,
        scope=scope,
        keywords=keywords,
        target_label_name=target_label_name,
        has_attachment=has_attachment,
    )

    if not email:
        return JsonResponse({"ok": False, "message": "No account selected."}, status=400)
    if not keywords:
        return JsonResponse({"ok": False, "message": "Enter at least one keyword."}, status=400)

    from utilities.gmail_search_jobs import start_search_job

    job_id = start_search_job(email, label_id, scope, keywords, has_attachment)
    return JsonResponse({"ok": True, "job_id": job_id})
