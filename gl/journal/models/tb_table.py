from django.db import models


class TbTable(models.Model):
    """
    Cumulative signed balance per fiscal year and account (from Authorised ``GlLine`` rows).

    Debits positive, credits negative — same convention as ``GlLine.amount``.
    """

    fiscal_year = models.ForeignKey(
        "fiscal_years.FiscalYear",
        on_delete=models.PROTECT,
        related_name="tb_table_rows",
    )
    account_code = models.CharField(max_length=30, db_index=True)
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Cumulative signed balance for this FY and account (Dr +, Cr −).",
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tb_table"
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "account_code"],
                name="tb_table_fy_account_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.fiscal_year_id} {self.account_code} {self.amount}"
