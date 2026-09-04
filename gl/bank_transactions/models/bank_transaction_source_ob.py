from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Coalesce


class BankTransactionSourceOb(models.Model):
    source_ac = models.OneToOneField(
        "bank_transactions.SourceBankCashAc",
        to_field="source_ac",
        db_column="source_ac",
        on_delete=models.PROTECT,
        related_name="opening_balance",
    )
    ym = models.CharField(max_length=5)
    ob_debit = models.FloatField(blank=True, null=True)
    ob_credit = models.FloatField(blank=True, null=True)
    ob = models.GeneratedField(
        expression=(
            Coalesce(F("ob_debit"), Value(0.0)) - Coalesce(F("ob_credit"), Value(0.0))
        ),
        output_field=models.FloatField(),
        db_persist=True,
    )

    class Meta:
        db_table = "bank_transactions_source_ob"
        ordering = ["source_ac"]

    def __str__(self):
        return f"{self.source_ac_id} {self.ym}"
    