from django.conf import settings
from django.db import models
from django.db.models import Q

from hr.grades.models import Grade
from hr.qualifications.models import Qualification


class TeamMember(models.Model):
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    called_as = models.CharField(max_length=80)
    code = models.CharField(max_length=4, unique=True)
    work_email = models.EmailField(max_length=254, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_team_member",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_team_members",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "team_members"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.code})"


def team_member_admin_label(obj):
    base = f"{obj.first_name} {obj.last_name} ({obj.code})"
    if obj.work_email:
        return f"{base} — {obj.work_email}"
    return base


def team_members_linkable_to_user(for_user):
    """
    Choices for linking a login to a team member.

    - Add user / unsaved user: only team members with **no** linked user yet.
    - Change user: same, plus the member already linked to this user (so you can
      keep or clear the link without the current row disappearing from the list).
    """
    qs = TeamMember.objects.order_by("first_name", "last_name", "code")
    if for_user is None:
        return qs.filter(user_id__isnull=True)
    user_pk = getattr(for_user, "pk", None)
    if not user_pk:
        return qs.filter(user_id__isnull=True)
    return qs.filter(Q(user_id__isnull=True) | Q(user_id=user_pk))


def link_user_to_team_member(user, team_member):
    """Clear any prior link for user, then optionally set team_member.user."""
    TeamMember.objects.filter(user=user).update(user=None)
    if team_member is not None:
        TeamMember.objects.filter(pk=team_member.pk).update(user=user)


class TeamMemberRollPeriod(models.Model):
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.CASCADE,
        related_name="roll_periods",
    )
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_team_member_roll_periods",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "team_member_roll_periods"
        ordering = ["-from_date", "-id"]

    def __str__(self):
        to_label = self.to_date.isoformat() if self.to_date else "Present"
        return f"{self.team_member.code}: {self.from_date.isoformat()} - {to_label}"


class TeamMemberQualificationPeriod(models.Model):
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.CASCADE,
        related_name="qualification_periods",
    )
    qualification = models.ForeignKey(
        Qualification,
        on_delete=models.PROTECT,
        related_name="team_member_periods",
    )
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_team_member_qualification_periods",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "team_member_qualification_periods"
        ordering = ["-from_date", "-id"]

    def __str__(self):
        to_label = self.to_date.isoformat() if self.to_date else "Present"
        return (
            f"{self.team_member.code}: {self.qualification.qualification_code} "
            f"{self.from_date.isoformat()} - {to_label}"
        )


class TeamMemberGradePeriod(models.Model):
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.CASCADE,
        related_name="grade_periods",
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        related_name="team_member_periods",
    )
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_team_member_grade_periods",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "team_member_grade_periods"
        ordering = ["-from_date", "-id"]

    def __str__(self):
        to_label = self.to_date.isoformat() if self.to_date else "Present"
        return (
            f"{self.team_member.code}: {self.grade.grade_code} "
            f"{self.from_date.isoformat()} - {to_label}"
        )
