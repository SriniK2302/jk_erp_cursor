from django.db import models


class BankTransactionSourceOb(models.Model):
    source_ac = models.OneToOneField(
        "bank_transactions.SourceBankCashAc",
        to_field="source_ac",
        db_column="source_ac",
        on_delete=models.PROTECT,
        related_name="opening_balance",
    )
    ym = models.CharField(max_length=5)
    ob = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "bank_transactions_source_ob"
        ordering = ["source_ac"]

    def __str__(self):
        return f"{self.source_ac_id} {self.ym}"
    