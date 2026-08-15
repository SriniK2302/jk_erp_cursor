from django.conf import settings
from django.db import models

from gl.fiscal_years.models import FiscalYear
from sales.clients.models import Client
from sales.services.models import Service

from .invoice_status import InvoiceStatus


class Invoice(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    invoice_date = models.DateField()
    invoice_no = models.CharField(max_length=40)
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    inv_taxable_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Invoice taxable value (Inv Tv).",
    )
    taxes = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    inv_gross = models.DecimalField(max_digits=14, decimal_places=2)
    narration = models.TextField(
        blank=True,
        default="",
        help_text="Optional text printed on the invoice (e.g. scope or reference).",
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.FRESH,
        db_index=True,
        help_text="Fresh when created; bulk post from the invoice list creates GL and sets Authorised.",
    )
    posted_gl_header = models.OneToOneField(
        "gl_journal.GlHeader",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posted_from_invoice",
        help_text="Authorised GL voucher created when this invoice was posted from Sales.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_invoices",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "invoice_no"],
                name="uq_invoice_client_invoice_no",
            ),
        ]

    def __str__(self):
        return f"{self.invoice_no} · {self.client.client_short_name}"
