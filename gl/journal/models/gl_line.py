from django.core.exceptions import ValidationError
from django.db import models

from .amount_utils import gl_amount_rounded
from .gl_header import GlHeader


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
