from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from hr.teams.models import TeamMember, team_member_admin_label, team_members_linkable_to_user

from .forms import UserAccountForm


@login_required
def setup_users(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    User = get_user_model()
    users = User.objects.order_by("username").select_related("linked_team_member")
    return render(
        request,
        "admin/setup_users.html",
        {"users": users},
    )


@login_required
@require_GET
def team_member_search_json(request):
    """AJAX: search team members (roster) eligible to link; not a user search."""
    if not request.user.is_superuser:
        raise PermissionDenied
    User = get_user_model()
    q = (request.GET.get("q") or "").strip()
    for_user_pk = request.GET.get("for_user")
    for_user = None
    if for_user_pk:
        for_user = get_object_or_404(User, pk=for_user_pk)

    qs = team_members_linkable_to_user(for_user)
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(called_as__icontains=q)
            | Q(code__icontains=q)
            | Q(work_email__icontains=q)
        )

    link_pk = None
    if for_user and for_user.pk:
        link_pk = (
            TeamMember.objects.filter(user_id=for_user.pk)
            .values_list("pk", flat=True)
            .first()
        )
    if link_pk:
        qs = qs.annotate(
            _prio=Case(
                When(pk=link_pk, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("_prio", "first_name", "last_name", "code")
    else:
        qs = qs.order_by("first_name", "last_name", "code")

    rows = [
        {"id": m.pk, "label": team_member_admin_label(m)} for m in qs.distinct()[:50]
    ]
    return JsonResponse(rows, safe=False)


@login_required
def setup_user_edit(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    User = get_user_model()
    account = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            return redirect("setup_users")
    else:
        form = UserAccountForm(instance=account)
    return render(
        request,
        "admin/setup_user_edit.html",
        {"form": form, "account": account},
    )
