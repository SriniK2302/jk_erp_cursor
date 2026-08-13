from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

_TWO_DP = Decimal("0.01")


def gl_amount_rounded(value) -> Decimal:
    """Money to 2 decimal places (half-up), for GL line amounts."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(_TWO_DP, rounding=ROUND_HALF_UP)


class GlHeader(models.Model):
    """Journal header: one logical GL transaction (voucher / document)."""

    class Source(models.TextChoices):
        SALES = "Sales", "Sales"
        PURCHASES = "Purchases", "Purchases"
        PAYROLL = "Payroll", "Payroll"
        FA = "FA", "FA"
        JV = "JV", "JV"
        CASH = "Cash", "Cash"
        BANK = "Bank", "Bank"
        OTHER = "Other", "Other"

    class Status(models.TextChoices):
        FRESH = "fresh", "Fresh"
        AUTHORISED = "authorised", "Authorised"

    rec_id = models.BigAutoField(primary_key=True)
    tran_date = models.DateField(db_index=True)
    tran_id = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Business transaction id (document / batch id within source).",
    )
    source = models.CharField(max_length=20, choices=Source.choices, db_index=True)
    narration = models.TextField(blank=True, default="")
    ym = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="Reporting month key, e.g. M YYYY MM as stored by your convention.",
    )
    line_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.FRESH,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_gl_headers",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gl_header"
        ordering = ["-tran_date", "-rec_id"]

    def __str__(self):
        return f"{self.source} {self.tran_id} @ {self.tran_date}"

    def save(self, *args, **kwargs):
        if self.pk:
            prior = GlHeader.objects.filter(pk=self.pk).values("status").first()
            if prior and prior["status"] == self.Status.AUTHORISED:
                raise ValidationError(
                    "Authorised GL header cannot be edited. Create a reversal/adjustment entry instead."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.AUTHORISED:
            raise ValidationError(
                "Authorised GL header cannot be deleted. Create a reversal entry instead."
            )
        return super().delete(*args, **kwargs)


class GlLine(models.Model):
    """Journal line: one leg of a GL header."""

    rec_id = models.BigAutoField(primary_key=True)
    header = models.ForeignKey(
        GlHeader,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_no = models.PositiveSmallIntegerField()
    account = models.ForeignKey(
        "config.ChartOfAccount",
        on_delete=models.PROTECT,
        related_name="gl_lines",
        to_field="account_code",
        db_column="account_code",
    )
    line_description = models.CharField(max_length=500, blank=True, default="")
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Signed: debit positive (+), credit negative (−).",
    )
    ym = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="Line reporting month (M YYYY MM as stored).",
    )
    rm_or = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="RM / OR month key (M YYYY MM as stored).",
    )
    value_ym = models.CharField(
        max_length=12,
        blank=True,
        default="",
        db_index=True,
        help_text="Value month (M YYYY MM as stored).",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gl_line"
        ordering = ["header", "line_no"]
        constraints = [
            models.UniqueConstraint(fields=["header", "line_no"], name="gl_line_header_line_no_uniq"),
        ]

    def save(self, *args, **kwargs):
        header_status = getattr(self.header, "status", None)
        if header_status is None and self.header_id:
            header_status = (
                GlHeader.objects.filter(pk=self.header_id).values_list("status", flat=True).first()
            )

        if header_status == GlHeader.Status.AUTHORISED:
            if not self.pk:
                raise ValidationError(
                    "Cannot add lines to an authorised GL header."
                )
            prior = GlLine.objects.filter(pk=self.pk).values(
                "header_id",
                "line_no",
                "account_id",
                "line_description",
                "amount",
                "ym",
                "rm_or",
                "value_ym",
            ).first()
            if prior is None:
                raise ValidationError("Cannot modify an authorised GL line.")
            changed_non_value_period = any(
                [
                    prior["header_id"] != self.header_id,
                    prior["line_no"] != self.line_no,
                    prior["account_id"] != self.account_id,
                    prior["line_description"] != self.line_description,
                    gl_amount_rounded(prior["amount"]) != gl_amount_rounded(self.amount),
                    prior["ym"] != self.ym,
                    prior["rm_or"] != self.rm_or,
                ]
            )
            if changed_non_value_period:
                raise ValidationError(
                    "For authorised GL data, only value period can be edited."
                )
        self.amount = gl_amount_rounded(self.amount)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        header_status = getattr(self.header, "status", None)
        if header_status is None and self.header_id:
            header_status = (
                GlHeader.objects.filter(pk=self.header_id).values_list("status", flat=True).first()
            )
        if header_status == GlHeader.Status.AUTHORISED:
            raise ValidationError(
                "Cannot delete lines from an authorised GL header."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.header_id} line {self.line_no} {self.account_id}"


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
