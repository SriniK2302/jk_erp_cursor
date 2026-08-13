from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from hr.teams.models import (
    TeamMember,
    link_user_to_team_member,
    team_member_admin_label,
    team_members_linkable_to_user,
)

from config.forms import clean_team_member_choice
from config.widgets import TeamMemberPickerWidget

User = get_user_model()

MODULE_GROUP_MAP = {
    "engagements": "module_engagements",
    "setup": "module_setup",
    "tools": "module_tools",
}


class UserAccountForm(forms.ModelForm):
    """Edit login user profile fields and optional 1:1 link to a team member."""

    team_member = forms.ModelChoiceField(
        queryset=TeamMember.objects.none(),
        required=False,
        label="Linked team member (optional)",
        help_text=(
            "Search loads matching team members from the server (not users). "
            "Use one checkbox to link, or clear. Only unmapped members are offered (plus "
            "the current link when editing)."
        ),
        widget=TeamMemberPickerWidget(),
    )
    can_use_engagements = forms.BooleanField(
        required=False,
        label="Can use Engagements",
    )
    can_use_setup = forms.BooleanField(
        required=False,
        label="Can use Setup",
    )
    can_use_tools = forms.BooleanField(
        required=False,
        label="Can use Tools & utilities",
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "is_active"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "input-medium"}),
            "first_name": forms.TextInput(attrs={"class": "input-medium"}),
            "last_name": forms.TextInput(attrs={"class": "input-medium"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = (
            "Email for this login (sign-in identity and notifications). "
            "It can differ from the team member’s optional work email on the Teams screen."
        )
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
        current_groups = set(
            self.instance.groups.values_list("name", flat=True)
            if self.instance and self.instance.pk
            else []
        )
        self.fields["can_use_engagements"].initial = (
            MODULE_GROUP_MAP["engagements"] in current_groups
        )
        self.fields["can_use_setup"].initial = MODULE_GROUP_MAP["setup"] in current_groups
        self.fields["can_use_tools"].initial = MODULE_GROUP_MAP["tools"] in current_groups

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise forms.ValidationError("Email is required.")
        return email

    def clean_team_member(self):
        return clean_team_member_choice(self.instance, self.cleaned_data.get("team_member"))

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            link_user_to_team_member(user, self.cleaned_data.get("team_member"))
            wanted = {
                MODULE_GROUP_MAP["engagements"]: self.cleaned_data.get(
                    "can_use_engagements", False
                ),
                MODULE_GROUP_MAP["setup"]: self.cleaned_data.get("can_use_setup", False),
                MODULE_GROUP_MAP["tools"]: self.cleaned_data.get("can_use_tools", False),
            }
            for group_name, enabled in wanted.items():
                group, _ = Group.objects.get_or_create(name=group_name)
                if enabled:
                    user.groups.add(group)
                else:
                    user.groups.remove(group)
        return user
