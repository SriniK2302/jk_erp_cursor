from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GradeForm
from .models import Grade


@login_required
def grades(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            grade = get_object_or_404(Grade, pk=request.POST.get("pk"))
            grade.delete()
            return redirect("grades")
        return redirect("grades")

    return render(
        request,
        "grades/grades.html",
        {
            "grades": Grade.objects.select_related("created_by").all(),
        },
    )


def _grade_form_view(request, instance=None):
    if request.method == "POST":
        form = GradeForm(request.POST, instance=instance)
        if form.is_valid():
            grade = form.save(commit=False)
            if instance is None:
                grade.created_by = request.user
            grade.save()
            return redirect("grades")
    else:
        form = GradeForm(instance=instance)

    return render(
        request,
        "grades/grade_form.html",
        {
            "form": form,
            "grade": instance,
        },
    )


@login_required
def grade_create(request):
    return _grade_form_view(request)


@login_required
def grade_edit(request, pk):
    grade = get_object_or_404(Grade, pk=pk)
    return _grade_form_view(request, instance=grade)
