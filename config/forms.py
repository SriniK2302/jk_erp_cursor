from django import forms

from hr.teams.models import TeamMember

from .models import ChartOfAccount, SalesLedgerSettings, SmtpMailSettings, UserTodo


def clean_team_member_choice(instance, member):
    if member is None:
        return member
    existing_user_id = (
        TeamMember.objects.filter(pk=member.pk)
        .values_list("user_id", flat=True)
        .first()
    )
    if existing_user_id and (not instance.pk or existing_user_id != instance.pk):
        raise forms.ValidationError(
            "That team member is already linked to another user."
        )
    return member


class SmtpMailSettingsForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Zoho app-specific password recommended. Leave blank when saving to keep the current password.",
    )

    class Meta:
        model = SmtpMailSettings
        fields = [
            "enabled",
            "smtp_host",
            "smtp_port",
            "use_tls",
            "use_ssl",
            "username",
            "password",
            "default_from_email",
        ]
        widgets = {
            "smtp_host": forms.TextInput(attrs={"class": "input-long"}),
            "smtp_port": forms.NumberInput(attrs={"class": "input-compact"}),
            "username": forms.EmailInput(attrs={"class": "input-long"}),
            "default_from_email": forms.EmailInput(attrs={"class": "input-long"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].required = False
        if not self.instance.pk:
            return
        prior = SmtpMailSettings.objects.filter(pk=self.instance.pk).values_list(
            "password", flat=True
        ).first()
        if prior:
            self.fields["password"].help_text = (
                "Leave blank to keep the existing password. "
                "Zoho app-specific password recommended."
            )

    def clean(self):
        data = super().clean()
        if data.get("use_tls") and data.get("use_ssl"):
            raise forms.ValidationError("Enable either TLS (e.g. port 587) or SSL (e.g. port 465), not both.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd:
            obj.password = pwd
        elif obj.pk:
            prev = SmtpMailSettings.objects.filter(pk=obj.pk).values_list("password", flat=True).first()
            obj.password = prev or ""
        if commit:
            obj.save()
        return obj


class UserTodoForm(forms.ModelForm):
    class Meta:
        model = UserTodo
        fields = ["title", "description", "target_date"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input-long"}),
            "description": forms.Textarea(
                attrs={"class": "input-long", "rows": 5, "placeholder": "Optional details"}
            ),
            "target_date": forms.DateInput(
                attrs={"type": "date", "class": "input-compact"}
            ),
        }


class SalesLedgerSettingsForm(forms.ModelForm):
    class Meta:
        model = SalesLedgerSettings
        fields = [
            "service_income_account",
            "cgst_output_account",
            "sgst_output_account",
            "igst_output_account",
            "sales_ledger_control_account",
        ]
        labels = {
            "service_income_account": "Service account (income)",
            "cgst_output_account": "CGST output account",
            "sgst_output_account": "SGST output account",
            "igst_output_account": "IGST output account",
            "sales_ledger_control_account": "Sales Ledger Control Account (receivables)",
        }
        widgets = {
            "service_income_account": forms.Select(attrs={"class": "input-long"}),
            "cgst_output_account": forms.Select(attrs={"class": "input-long"}),
            "sgst_output_account": forms.Select(attrs={"class": "input-long"}),
            "igst_output_account": forms.Select(attrs={"class": "input-long"}),
            "sales_ledger_control_account": forms.Select(attrs={"class": "input-long"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        all_coa = ChartOfAccount.objects.order_by("account_code", "account_name")
        self.fields["service_income_account"].queryset = all_coa.filter(
            plbs=ChartOfAccount.PLBS_PL,
            plbs_type=ChartOfAccount.TYPE_INCOME,
        )
        liability_qs = all_coa.filter(
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_LIABILITY,
        )
        self.fields["cgst_output_account"].queryset = liability_qs
        self.fields["sgst_output_account"].queryset = liability_qs
        self.fields["igst_output_account"].queryset = liability_qs
        self.fields["sales_ledger_control_account"].queryset = all_coa.filter(
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
        )
        for name, field in self.fields.items():
            field.required = False
            field.empty_label = "Choose account..."
            field.label_from_instance = (
                lambda coa: f"{coa.account_code} - {coa.account_name}"
            )


