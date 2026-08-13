from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from hr.teams.models import TeamMember
from hr.teams.rules import (
    get_team_grade_mapping_defaults,
    is_grade_period_to_date_locked,
)

from .forms import TeamGradeMapForm
from .models import TeamMemberGradePeriod


@login_required
def team_grade_maps(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            grade_map = get_object_or_404(
                TeamMemberGradePeriod,
                pk=request.POST.get("pk"),
            )
            grade_map.delete()
            return redirect("team_grade_maps")

    return render(
        request,
        "team_grade_maps/team_grade_maps.html",
        {
            "grade_maps": TeamMemberGradePeriod.objects.select_related(
                "team_member",
                "grade",
            ),
        },
    )


def _team_grade_map_form_view(request, instance=None):
    if request.method == "POST":
        form = TeamGradeMapForm(request.POST, instance=instance)
        if form.is_valid():
            grade_map = form.save(commit=False)
            if instance is None:
                grade_map.created_by = request.user
            grade_map.save()
            return redirect("team_grade_maps")
    else:
        form = TeamGradeMapForm(instance=instance)
        if instance is None:
            member_id = request.GET.get("team_member")
            if member_id:
                member = TeamMember.objects.filter(pk=member_id).first()
                if member is not None:
                    defaults = get_team_grade_mapping_defaults(member)
                    if defaults["has_roll_period"]:
                        form = TeamGradeMapForm(
                            initial={
                                "team_member": member.pk,
                                "from_date": defaults["from_date"],
                                "to_date": defaults["to_date"],
                            },
                        )

    context = {
        "form": form,
        "grade_map": instance,
    }
    if instance is not None:
        context["to_date_locked"] = is_grade_period_to_date_locked(instance)

    return render(
        request,
        "team_grade_maps/team_grade_map_form.html",
        context,
    )


@login_required
def team_grade_map_create(request):
    return _team_grade_map_form_view(request)


@login_required
def team_grade_map_edit(request, pk):
    grade_map = get_object_or_404(TeamMemberGradePeriod, pk=pk)
    return _team_grade_map_form_view(request, instance=grade_map)


@login_required
def team_grade_map_defaults(request):
    member_id = request.GET.get("team_member")
    if not member_id:
        return JsonResponse({"error": "team_member is required"}, status=400)

    member = get_object_or_404(TeamMember, pk=member_id)
    period = None
    period_id = request.GET.get("period_id")
    if period_id:
        period = get_object_or_404(
            TeamMemberGradePeriod,
            pk=period_id,
            team_member=member,
        )

    defaults = get_team_grade_mapping_defaults(
        member,
        period=period,
        exclude_period_id=period.pk if period else None,
    )

    return JsonResponse(
        {
            "has_roll_period": defaults["has_roll_period"],
            "from_date": (
                defaults["from_date"].isoformat() if defaults["from_date"] else ""
            ),
            "to_date": defaults["to_date"].isoformat() if defaults["to_date"] else "",
            "is_to_date_locked": defaults["is_to_date_locked"],
        }
    )
