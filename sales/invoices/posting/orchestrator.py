"""Sequences journal, TB delta, and invoice-link posting inside one caller transaction."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from gl.journal.models import GlHeader
from gl.journal.posting import GlTbDeltaPosting

from ..models import Invoice, InvoiceStatus
from .invoice_gl_link_posting import InvoiceGlAuthorisedLinkPosting
from .sales_gl_journal_posting import SalesGlJournalPosting


class SalesInvoiceGlPostOrchestrator:
    """
    Runs discrete posting steps in order for each Fresh invoice.

    ``bulk_post_fresh_invoices_to_gl`` opens a single ``transaction.atomic()`` so all
    steps for all selected invoices commit or roll back together.
    """

    def __init__(self) -> None:
        self._journal = SalesGlJournalPosting()
        self._tb_delta = GlTbDeltaPosting()
        self._invoice_link = InvoiceGlAuthorisedLinkPosting()

    def post_fresh_invoice_to_gl(self, *, invoice: Invoice, user) -> GlHeader:
        """
        Create GL voucher, apply TB deltas, mark invoice Authorised.

        Caller must hold a row lock on the invoice (e.g. ``select_for_update`` inside ``atomic``).
        """
        self._ensure_invoice_postable(invoice)
        hdr = self._journal.execute(invoice=invoice, user=user)
        self._tb_delta.execute(header=hdr)
        self._invoice_link.execute(invoice=invoice, header=hdr)
        return hdr

    @staticmethod
    def _ensure_invoice_postable(invoice: Invoice) -> None:
        if invoice.status != InvoiceStatus.FRESH:
            raise ValidationError(f"Invoice {invoice.invoice_no} is not Fresh; cannot post.")
        if invoice.posted_gl_header_id:
            raise ValidationError(f"Invoice {invoice.invoice_no} is already posted to GL.")

    def bulk_post_fresh_invoices_to_gl(
        self, *, invoice_pks: list[int], user
    ) -> tuple[int, list[str]]:
        """
        Post all given invoices in one transaction (all succeed or none).

        Returns (posted_count, error_messages). On any error, rolls back and returns (0, [msg, ...]).
        """
        pks = sorted({int(pk) for pk in invoice_pks if str(pk).isdigit()})
        if not pks:
            return 0, ["No invoices selected."]

        try:
            with transaction.atomic():
                qs = (
                    Invoice.objects.filter(pk__in=pks)
                    .select_for_update()
                    .order_by("invoice_date", "pk")
                )
                invoices = list(qs)
                if len(invoices) != len(pks):
                    missing = set(pks) - {i.pk for i in invoices}
                    raise ValidationError(f"Unknown invoice id(s): {sorted(missing)}")

                for inv in invoices:
                    self.post_fresh_invoice_to_gl(invoice=inv, user=user)
            return len(invoices), []
        except ValidationError as e:
            msgs = list(getattr(e, "messages", []) or []) or [str(e)]
            return 0, msgs
        except Exception as e:
            return 0, [str(e)]
