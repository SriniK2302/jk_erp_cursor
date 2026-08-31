from django.db import models


class SourceBankCashAc(models.Model):
    source_ac = models.CharField(max_length=15, unique=True)
    fb_code = models.CharField(max_length=2)

    class Meta:
        db_table = "source_bank_cash_acs"
        ordering = ["source_ac"]

    def __str__(self):
        return self.source_ac
    