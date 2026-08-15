from django.db import models

from .invoice import Invoice


class InvUdinMap(models.Model):
    """
    Links one invoice to one or more UDIN fee lines (same UDIN may appear twice with different fees).
    Drives generation of Service rows in invoice_lines.
    """

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="inv_udin_maps",
    )
    line_no = models.PositiveSmallIntegerField(
        help_text="Fee line number (matches Service line order in invoice_lines).",
    )
    udin = models.ForeignKey(
        "udins.Udin",
        on_delete=models.PROTECT,
        related_name="inv_udin_map_entries",
    )
    service_desc = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Description printed for this fee line (e.g. Fee for …).",
    )
    line_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "inv_udin_map"
        ordering = ["invoice_id", "line_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_no"],
                name="uq_inv_udin_map_invoice_line",
            ),
        ]

    def __str__(self):
        return f"{self.invoice_id} map L{self.line_no} {self.udin_id}"
