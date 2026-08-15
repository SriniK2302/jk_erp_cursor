from django.db import models


class TbTableMonth(models.Model):
    """
    Signed GL activity by fiscal year, **calendar month** of posting, and account.

    ``period_from`` / ``period_to`` are the first and last day of the month of
    ``GlHeader.tran_date``. Same amount convention as ``GlLine`` (Dr +, Cr −).
    """

    fiscal_year = models.ForeignKey(
        "fiscal_years.FiscalYear",
        on_delete=models.PROTECT,
        related_name="tb_table_month_rows",
    )
    period_from = models.DateField(
        db_index=True,
        help_text="First calendar day of the posting month.",
    )
    period_to = models.DateField(
        help_text="Last calendar day of the posting month.",
    )
    account_code = models.CharField(max_length=30, db_index=True)
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Net signed amount for this FY, month, and account.",
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tb_table_month"
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "period_from", "account_code"],
                name="tb_table_month_fy_period_account_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.fiscal_year_id} {self.period_from} {self.account_code} {self.amount}"
