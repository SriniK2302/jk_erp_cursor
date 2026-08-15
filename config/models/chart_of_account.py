from django.conf import settings
from django.db import models


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
