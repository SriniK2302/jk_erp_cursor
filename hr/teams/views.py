from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import (
    TeamMemberForm,
    TeamMemberQualificationPeriodForm,
    TeamMemberRollPeriodForm,
)
from .models import (
    TeamMember,
    TeamMemberQualificationPeriod,
    TeamMemberRollPeriod,
)


@login_required
def teams(request):
    selected_member_id = request.GET.get("member")

    selected_member = None

    if selected_member_id:
        selected_member = get_object_or_404(TeamMember, pk=selected_member_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete_member":
            member = get_object_or_404(TeamMember, pk=request.POST.get("pk"))
            member.delete()
            return redirect("teams")

        if action == "delete_roll_period":
            period_pk = request.POST.get("period_pk")
            member_id = request.POST.get("member_id")
            period = get_object_or_404(
                TeamMemberRollPeriod,
                pk=period_pk,
                team_member_id=member_id,
            )
            period.delete()
            return redirect(f"{request.path}?member={member_id}")

        if action == "delete_qualification_period":
            qualification_period_pk = request.POST.get("qualification_period_pk")
            member_id = request.POST.get("member_id")
            qualification_period = get_object_or_404(
                TeamMemberQualificationPeriod,
                pk=qualification_period_pk,
                team_member_id=member_id,
            )
            qualification_period.delete()
            return redirect(f"{request.path}?member={member_id}")

    roll_periods = (
        selected_member.roll_periods.select_related("created_by")
        if selected_member is not None
        else []
    )
    qualification_periods = (
        selected_member.qualification_periods.select_related(
            "qualification", "created_by"
        )
        if selected_member is not None
        else []
    )

    return render(
        request,
        "teams/teams.html",
        {
            "members": TeamMember.objects.select_related("created_by", "user").all(),
            "selected_member": selected_member,
            "roll_periods": roll_periods,
            "qualification_periods": qualification_periods,
        },
    )


def _team_member_form_view(request, instance=None):
    if request.method == "POST":
        form = TeamMemberForm(request.POST, instance=instance)
        if form.is_valid():
            team_member = form.save(commit=False)
            if instance is None:
                team_member.created_by = request.user
            team_member.save()
            return redirect(f"{reverse('teams')}?member={team_member.pk}")
    else:
        form = TeamMemberForm(instance=instance)

    return render(
        request,
        "teams/team_member_form.html",
        {
            "form": form,
            "member": instance,
        },
    )


@login_required
def team_member_create(request):
    return _team_member_form_view(request)


@login_required
def team_member_edit(request, pk):
    member = get_object_or_404(TeamMember, pk=pk)
    return _team_member_form_view(request, instance=member)


def _roll_period_form_view(request, member, instance=None):
    if request.method == "POST":
        form = TeamMemberRollPeriodForm(request.POST, instance=instance)
        if form.is_valid():
            roll_period = form.save(commit=False)
            if instance is None:
                roll_period.team_member = member
                roll_period.created_by = request.user
            roll_period.save()
            return redirect(f"{reverse('teams')}?member={member.pk}")
    else:
        form = TeamMemberRollPeriodForm(instance=instance)

    return render(
        request,
        "teams/roll_period_form.html",
        {
            "form": form,
            "member": member,
            "roll_period": instance,
        },
    )


@login_required
def roll_period_create(request, member_pk):
    member = get_object_or_404(TeamMember, pk=member_pk)
    return _roll_period_form_view(request, member=member)


@login_required
def roll_period_edit(request, member_pk, pk):
    member = get_object_or_404(TeamMember, pk=member_pk)
    roll_period = get_object_or_404(TeamMemberRollPeriod, pk=pk, team_member=member)
    return _roll_period_form_view(request, member=member, instance=roll_period)


def _qualification_period_form_view(request, member, instance=None):
    if request.method == "POST":
        form = TeamMemberQualificationPeriodForm(request.POST, instance=instance)
        if form.is_valid():
            qualification_period = form.save(commit=False)
            if instance is None:
                qualification_period.team_member = member
                qualification_period.created_by = request.user
            qualification_period.save()
            return redirect(f"{reverse('teams')}?member={member.pk}")
    else:
        form = TeamMemberQualificationPeriodForm(instance=instance)

    return render(
        request,
        "teams/qualification_period_form.html",
        {
            "form": form,
            "member": member,
            "qualification_period": instance,
        },
    )


@login_required
def qualification_period_create(request, member_pk):
    member = get_object_or_404(TeamMember, pk=member_pk)
    return _qualification_period_form_view(request, member=member)


@login_required
def qualification_period_edit(request, member_pk, pk):
    member = get_object_or_404(TeamMember, pk=member_pk)
    qualification_period = get_object_or_404(
        TeamMemberQualificationPeriod,
        pk=pk,
        team_member=member,
    )
    return _qualification_period_form_view(
        request,
        member=member,
        instance=qualification_period,
    )


