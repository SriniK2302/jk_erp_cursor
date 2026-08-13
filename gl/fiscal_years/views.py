from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import FiscalYearForm
from .models import FiscalYear


@login_required
def fiscal_years(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            fiscal_year = get_object_or_404(FiscalYear, pk=request.POST.get("pk"))
            fiscal_year.delete()
            return redirect("fiscal_years")
        return redirect("fiscal_years")

    return render(
        request,
        "fiscal_years/fiscal_years.html",
        {
            "fiscal_years": FiscalYear.objects.select_related("created_by").all(),
        },
    )


def _fiscal_year_form_view(request, instance=None):
    if request.method == "POST":
        form = FiscalYearForm(request.POST, instance=instance)
        if form.is_valid():
            fiscal_year = form.save(commit=False)
            if instance is None:
                fiscal_year.created_by = request.user
            fiscal_year.save()
            return redirect("fiscal_years")
    else:
        form = FiscalYearForm(instance=instance)

    return render(
        request,
        "fiscal_years/fiscal_year_form.html",
        {
            "form": form,
            "fiscal_year": instance,
        },
    )


@login_required
def fiscal_year_create(request):
    return _fiscal_year_form_view(request)


@login_required
def fiscal_year_edit(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    return _fiscal_year_form_view(request, instance=fiscal_year)
