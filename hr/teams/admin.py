from django.contrib import admin

from .models import (
    TeamMember,
    TeamMemberGradePeriod,
    TeamMemberQualificationPeriod,
    TeamMemberRollPeriod,
)


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    """Login link is edited only from Authentication → Users (single source of truth)."""

    readonly_fields = ("user",)

    list_display = (
        "first_name",
        "last_name",
        "called_as",
        "code",
        "work_email",
        "user",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "first_name",
        "last_name",
        "called_as",
        "code",
        "work_email",
        "user__username",
    )


@admin.register(TeamMemberRollPeriod)
class TeamMemberRollPeriodAdmin(admin.ModelAdmin):
    list_display = ("team_member", "from_date", "to_date", "notes", "created_on", "updated_on")
    search_fields = ("team_member__first_name", "team_member__last_name", "team_member__code", "notes")


@admin.register(TeamMemberQualificationPeriod)
class TeamMemberQualificationPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "team_member",
        "qualification",
        "from_date",
        "to_date",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "team_member__first_name",
        "team_member__last_name",
        "team_member__code",
        "qualification__qualification_desc",
        "qualification__qualification_code",
    )


@admin.register(TeamMemberGradePeriod)
class TeamMemberGradePeriodAdmin(admin.ModelAdmin):
    list_display = (
        "team_member",
        "grade",
        "from_date",
        "to_date",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "team_member__first_name",
        "team_member__last_name",
        "team_member__code",
        "grade__grade_desc",
        "grade__grade_code",
    )
