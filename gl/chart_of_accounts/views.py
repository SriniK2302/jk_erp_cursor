from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from config.models import ChartOfAccount
from config.views import MODULE_SETUP, _has_module_access

from .forms import ChartOfAccountForm


@login_required
def chart_of_accounts(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            row = get_object_or_404(ChartOfAccount, pk=request.POST.get("pk"))
            row.delete()
            return redirect("chart_of_accounts")
        return redirect("chart_of_accounts")

    return render(
        request,
        "chart_of_accounts/chart_of_accounts.html",
        {"rows": ChartOfAccount.objects.select_related("created_by").all()},
    )


def _chart_of_account_form_view(request, instance=None):
    if request.method == "POST":
        form = ChartOfAccountForm(request.POST, instance=instance)
        if form.is_valid():
            row = form.save(commit=False)
            if instance is None:
                row.created_by = request.user
            row.save()
            return redirect("chart_of_accounts")
    else:
        form = ChartOfAccountForm(instance=instance)

    return render(
        request,
        "chart_of_accounts/chart_of_account_form.html",
        {"form": form, "row": instance},
    )


@login_required
def chart_of_account_create(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    return _chart_of_account_form_view(request)


@login_required
def chart_of_account_edit(request, pk):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    row = get_object_or_404(ChartOfAccount, pk=pk)
    return _chart_of_account_form_view(request, instance=row)


@login_required
@require_GET
def chart_of_account_next_code(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    plbs_type = (request.GET.get("plbs_type") or "").strip().upper()
    if not plbs_type:
        return JsonResponse({"code": "", "error": "plbs_type is required"}, status=400)
    try:
        code = ChartOfAccountForm._next_available_account_code(plbs_type=plbs_type)
    except Exception as exc:
        return JsonResponse({"code": "", "error": str(exc)}, status=400)
    return JsonResponse({"code": code})
