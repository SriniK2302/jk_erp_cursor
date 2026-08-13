from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import QualificationForm
from .models import Qualification


@login_required
def qualifications(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            qualification = get_object_or_404(
                Qualification, pk=request.POST.get("pk")
            )
            qualification.delete()
            return redirect("qualifications")
        return redirect("qualifications")

    return render(
        request,
        "qualifications/qualifications.html",
        {
            "qualifications": Qualification.objects.select_related("created_by").all(),
        },
    )


def _qualification_form_view(request, instance=None):
    if request.method == "POST":
        form = QualificationForm(request.POST, instance=instance)
        if form.is_valid():
            qualification = form.save(commit=False)
            if instance is None:
                qualification.created_by = request.user
            qualification.save()
            return redirect("qualifications")
    else:
        form = QualificationForm(instance=instance)

    return render(
        request,
        "qualifications/qualification_form.html",
        {
            "form": form,
            "qualification": instance,
        },
    )


@login_required
def qualification_create(request):
    return _qualification_form_view(request)


@login_required
def qualification_edit(request, pk):
    qualification = get_object_or_404(Qualification, pk=pk)
    return _qualification_form_view(request, instance=qualification)
