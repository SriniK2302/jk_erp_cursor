from django.conf import settings
from django.db import models


class BankStatementUpload(models.Model):
    source_ac = models.ForeignKey(
        "bank_transactions.SourceBankCashAc",
        to_field="source_ac",
        db_column="source_ac",
        on_delete=models.PROTECT,
        related_name="statement_uploads",
    )
    fiscal_year = models.ForeignKey(
        "fiscal_years.FiscalYear",
        on_delete=models.PROTECT,
        related_name="bank_statement_uploads",
    )
    statement_file = models.FileField(upload_to="bank_statements/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bank_statement_uploads",
        null=True,
        blank=True,
    )
    uploaded_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bank_statement_uploads"
        ordering = ["-uploaded_on"]

    def __str__(self):
        return f"{self.source_ac_id} {self.fiscal_year_id} {self.statement_file.name}"
    