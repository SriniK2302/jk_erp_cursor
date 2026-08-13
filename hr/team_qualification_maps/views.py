from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TeamQualificationMapForm
from .models import TeamMemberQualificationPeriod


@login_required
def team_qualification_maps(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            qualification_map = get_object_or_404(
                TeamMemberQualificationPeriod,
                pk=request.POST.get("pk"),
            )
            qualification_map.delete()
            return redirect("team_qualification_maps")

    return render(
        request,
        "team_qualification_maps/team_qualification_maps.html",
        {
            "qualification_maps": TeamMemberQualificationPeriod.objects.select_related(
                "team_member",
                "qualification",
            ),
        },
    )


def _team_qualification_map_form_view(request, instance=None):
    if request.method == "POST":
        form = TeamQualificationMapForm(request.POST, instance=instance)
        if form.is_valid():
            qualification_map = form.save(commit=False)
            if instance is None:
                qualification_map.created_by = request.user
            qualification_map.save()
            return redirect("team_qualification_maps")
    else:
        form = TeamQualificationMapForm(instance=instance)

    return render(
        request,
        "team_qualification_maps/team_qualification_map_form.html",
        {
            "form": form,
            "qualification_map": instance,
        },
    )


@login_required
def team_qualification_map_create(request):
    return _team_qualification_map_form_view(request)


@login_required
def team_qualification_map_edit(request, pk):
    qualification_map = get_object_or_404(TeamMemberQualificationPeriod, pk=pk)
    return _team_qualification_map_form_view(request, instance=qualification_map)
