from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Coalesce


class BankTransactionSource(models.Model):
    source_ac = models.ForeignKey(
        "bank_transactions.SourceBankCashAc",
        to_field="source_ac",
        db_column="source_ac",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    tran_date = models.DateField()
    narration = models.CharField(max_length=1000, blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    net_debit = models.GeneratedField(
        expression=Coalesce(F("debit"), Value(0.0)) - Coalesce(F("credit"), Value(0.0)),
        output_field=models.FloatField(),
        db_persist=True,
    )
    closing_balance = models.FloatField(blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    value_date = models.DateField()
    tran_id = models.CharField(max_length=100, blank=True, null=True)
    fb_mapped = models.CharField(max_length=10, blank=True, null=True)
    posting_fb = models.CharField(max_length=10, blank=True, null=True)
    gl_account = models.CharField(max_length=150, blank=True, null=True)
    main_analysis = models.CharField(max_length=50, blank=True, null=True)
    sub_analysis = models.CharField(max_length=50, blank=True, null=True)
    tertiary_analysis = models.CharField(max_length=50, blank=True, null=True)
    ym = models.CharField(max_length=5, blank=True, null=True)
    account_type = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        db_table = "bank_transactions_source"
        ordering = ["source_ac", "tran_date"]

    def __str__(self):
        return f"{self.source_ac_id} {self.tran_date} {self.reference or ''}".strip()
    