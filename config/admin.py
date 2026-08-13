from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm as DjangoAdminUserCreationForm,
    UserChangeForm,
)
from django.urls import reverse

from hr.teams.models import (
    TeamMember,
    link_user_to_team_member,
    team_member_admin_label,
    team_members_linkable_to_user,
)

from .forms import clean_team_member_choice
from .models import SmtpMailSettings, UserTodo
from .widgets import TeamMemberPickerWidget


class AdminUserChangeForm(UserChangeForm):
    team_member = forms.ModelChoiceField(
        queryset=TeamMember.objects.none(),
        required=False,
        label="Linked team member",
        help_text=(
            "Optional: tie this login to one HR roster row. Search loads team members only. "
            "Pick at most one checkbox."
        ),
        widget=TeamMemberPickerWidget(),
    )

    class Meta(UserChangeForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["team_member"].queryset = team_members_linkable_to_user(self.instance)
        self.fields["team_member"].label_from_instance = team_member_admin_label

        initial_id = ""
        initial_label = ""
        if self.instance and self.instance.pk:
            try:
                linked = self.instance.linked_team_member
            except TeamMember.DoesNotExist:
                self.fields["team_member"].initial = None
            else:
                self.fields["team_member"].initial = linked.pk
                initial_id = str(linked.pk)
                initial_label = team_member_admin_label(linked)

        tid = (self.auto_id % "team_member") if self.auto_id else "team_member"
        self.fields["team_member"].widget = TeamMemberPickerWidget(
            attrs={
                "id": tid,
                "data_search_url": reverse("team_member_search"),
                "data_for_user": str(self.instance.pk) if self.instance.pk else "",
                "data_initial_id": initial_id,
                "data_initial_label": initial_label,
            }
        )

    def clean_team_member(self):
        return clean_team_member_choice(self.instance, self.cleaned_data.get("team_member"))


class AdminUserCreationForm(DjangoAdminUserCreationForm):
    """Matches Django admin user add (usable_password); optional team member link."""

    team_member = forms.ModelChoiceField(
        queryset=TeamMember.objects.none(),
        required=False,
        label="Linked team member",
        help_text=(
            "Optional. Search loads team members without a linked login yet. "
            "Pick at most one checkbox."
        ),
        widget=TeamMemberPickerWidget(),
    )

    class Meta(DjangoAdminUserCreationForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["team_member"].queryset = team_members_linkable_to_user(None)
        self.fields["team_member"].label_from_instance = team_member_admin_label

        tid = (self.auto_id % "team_member") if self.auto_id else "team_member"
        self.fields["team_member"].widget = TeamMemberPickerWidget(
            attrs={
                "id": tid,
                "data_search_url": reverse("team_member_search"),
                "data_for_user": "",
                "data_initial_id": "",
                "data_initial_label": "",
            }
        )

    def clean_team_member(self):
        return clean_team_member_choice(self.instance, self.cleaned_data.get("team_member"))


class UserAdmin(BaseUserAdmin):
    """User records in admin: superusers only."""

    form = AdminUserChangeForm
    add_form = AdminUserCreationForm

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "HR / roster",
            {
                "fields": ("team_member",),
                "description": (
                    "Map this user to a team member for HR, or leave unset. "
                    "Search queries the team roster (not users). Same link as Setup → Users."
                ),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "usable_password",
                    "password1",
                    "password2",
                    "team_member",
                ),
            },
        ),
    )

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if isinstance(form, (AdminUserChangeForm, AdminUserCreationForm)):
            link_user_to_team_member(obj, form.cleaned_data.get("team_member"))


@admin.register(UserTodo)
class UserTodoAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "target_date", "is_completed", "created_on")
    list_filter = ("is_completed",)
    search_fields = ("title", "description", "user__username")
    readonly_fields = ("created_on", "updated_on")
    ordering = ("-created_on",)

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)


@admin.register(SmtpMailSettings)
class SmtpMailSettingsAdmin(admin.ModelAdmin):
    list_display = ("enabled", "smtp_host", "smtp_port", "username", "updated_on")
    readonly_fields = ("updated_on",)

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        # Keep this singleton-like from admin as well.
        return bool(request.user.is_superuser) and not SmtpMailSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


# Registration runs in ConfigConfig.ready() so it happens after contrib.auth.admin.
