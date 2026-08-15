from django.db import models


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
