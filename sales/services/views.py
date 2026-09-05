from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ServiceForm
from .models import Service


@login_required
def services(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            service = get_object_or_404(Service, pk=request.POST.get("pk"))
            service.delete()
            return redirect("services")
        return redirect("services")

    return render(
        request,
        "services/services.html",
        {
            "services": Service.objects.select_related("created_by").all(),
        },
    )


def _service_form_view(request, instance=None):
    if request.method == "POST":
        form = ServiceForm(request.POST, instance=instance)
        if form.is_valid():
            service = form.save(commit=False)
            if instance is None:
                service.created_by = request.user
            service.save()
            next_url = request.GET.get("next")
            if next_url:
                sep = "&" if "?" in next_url else "?"
                return redirect(f"{next_url}{sep}new_service={service.pk}")
            return redirect("services")

    else:
        form = ServiceForm(instance=instance)

    return render(
        request,
        "services/service_form.html",
        {
            "form": form,
            "service": instance,
        },
    )


@login_required
def service_create(request):
    return _service_form_view(request)


@login_required
def service_edit(request, pk):
    service = get_object_or_404(Service, pk=pk)
    return _service_form_view(request, instance=service)
