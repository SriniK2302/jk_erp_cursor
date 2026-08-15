from django.db import models

from .invoice import Invoice


class InvoiceLine(models.Model):
    """One display / tax line on an invoice (service + GST components)."""

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="invoice_lines",
    )
    line_no = models.PositiveSmallIntegerField()
    line_type = models.CharField(max_length=16)
    line_base_amount = models.DecimalField(max_digits=14, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=2)
    item_amount = models.DecimalField(max_digits=14, decimal_places=2)
    line_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="For Service lines: printed description; tax lines leave blank.",
    )

    class Meta:
        db_table = "invoice_lines"
        ordering = ["invoice_id", "line_no"]

    def __str__(self):
        return f"{self.invoice_id} L{self.line_no} {self.line_type}"
