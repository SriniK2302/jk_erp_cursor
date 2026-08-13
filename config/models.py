from django.conf import settings
from django.db import models


class SmtpMailSettings(models.Model):
    """Singleton (pk=1): outbound SMTP (e.g. Zoho) for system emails such as team assignment notices."""

    enabled = models.BooleanField(
        default=False,
        help_text="When off, no emails are sent (assignment saves still succeed).",
    )
    smtp_host = models.CharField(
        max_length=120,
        default="smtppro.zoho.com",
        help_text="Zoho Mail: smtppro.zoho.com (organisation) or smtp.zoho.com (personal).",
    )
    smtp_port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(
        default=False,
        help_text="Use for port 465 (SSL). Do not enable both TLS and SSL.",
    )
    username = models.CharField(
        max_length=254,
        blank=True,
        help_text="Zoho mailbox address used to authenticate SMTP.",
    )
    password = models.CharField(
        max_length=255,
        blank=True,
        help_text="Zoho app-specific or account password (stored in DB; restrict who can edit).",
    )
    default_from_email = models.EmailField(
        max_length=254,
        blank=True,
        help_text="From address shown to recipients (often same as username).",
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "smtp_mail_settings"
        verbose_name = "SMTP mail settings"

    def __str__(self):
        return "SMTP mail settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SalesLedgerSettings(models.Model):
    """Singleton (pk=1): COA mappings used for invoice and receivable postings."""

    service_income_account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    cgst_output_account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    sgst_output_account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    igst_output_account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    sales_ledger_control_account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text="Receivables control account for invoice posting.",
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_ledger_settings"
        verbose_name = "Sales ledger settings"

    def __str__(self):
        return "Sales ledger settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class UserTodo(models.Model):
    """Personal to-do item for a login user (not shared across users)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todos",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional due or reminder date.",
    )
    is_completed = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_todos"
        ordering = ["-created_on"]

    def __str__(self):
        return self.title


class ChartOfAccount(models.Model):
    PLBS_PL = "PL"
    PLBS_BS = "BS"
    PLBS_CHOICES = (
        (PLBS_PL, "PL"),
        (PLBS_BS, "BS"),
    )

    TYPE_ASSET = "ASSET"
    TYPE_LIABILITY = "LIABILITY"
    TYPE_INCOME = "INCOME"
    TYPE_EXPENSES = "EXPENSES"
    PLBS_TYPE_CHOICES = (
        (TYPE_ASSET, "Asset"),
        (TYPE_LIABILITY, "Liability"),
        (TYPE_INCOME, "Income"),
        (TYPE_EXPENSES, "Expenses"),
    )

    account_name = models.CharField(max_length=150)
    account_code = models.CharField(max_length=30, unique=True)
    plbs = models.CharField(max_length=2, choices=PLBS_CHOICES)
    plbs_type = models.CharField(max_length=12, choices=PLBS_TYPE_CHOICES)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_chart_of_accounts",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chart_of_accounts"
        ordering = ["account_code", "account_name"]

    def __str__(self):
        return f"{self.account_code} - {self.account_name}"
