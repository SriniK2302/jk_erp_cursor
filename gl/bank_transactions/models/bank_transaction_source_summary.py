from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Coalesce


class BankTransactionSourceSummary(models.Model):
    source_ac = models.ForeignKey(
        "bank_transactions.SourceBankCashAc",
        to_field="source_ac",
        db_column="source_ac",
        on_delete=models.PROTECT,
        related_name="summaries",
    )
    ym = models.CharField(max_length=5)
    ob = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    cb = models.GeneratedField(
        expression=(
            Coalesce(F("ob"), Value(0.0))
            + Coalesce(F("debit"), Value(0.0))
            - Coalesce(F("credit"), Value(0.0))
        ),
        output_field=models.FloatField(),
        db_persist=True,
    )
    cb_from_statement = models.FloatField(blank=True, null=True)
    statement_upload = models.ForeignKey(
        "bank_transactions.BankStatementUpload",
        on_delete=models.SET_NULL,
        related_name="summary_rows",
        null=True,
        blank=True,
    )
    check_diff = models.GeneratedField(
        expression=(
            Coalesce(F("ob"), Value(0.0))
            + Coalesce(F("debit"), Value(0.0))
            - Coalesce(F("credit"), Value(0.0))
            - Coalesce(F("cb_from_statement"), Value(0.0))
        ),
        output_field=models.FloatField(),
        db_persist=True,
    )
    account_type = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        db_table = "bank_transactions_source_summary"
        ordering = ["source_ac", "ym"]

    def __str__(self):
        return f"{self.source_ac_id} {self.ym}"

    