from django.db import models


class SourceBankCashAc(models.Model):
    class AccountType(models.TextChoices):
        SAVINGS = "SB", "Savings Bank"
        CURRENT = "CA", "Current Account"
        CREDIT_CARD = "CC", "Credit Card"
        CASH_CREDIT = "CD", "Cash Credit"
        OVERDRAFT = "OD", "Overdraft"

    source_ac = models.CharField(max_length=15, unique=True)
    bank_name = models.CharField(max_length=50, blank=True, default="")
    account_type = models.CharField(
        max_length=2, blank=True, default="", choices=AccountType.choices
    )
    fb_code = models.CharField(max_length=5)

    class Meta:
        db_table = "source_bank_cash_acs"
        ordering = ["source_ac"]

    def __str__(self):
        return self.source_ac
    