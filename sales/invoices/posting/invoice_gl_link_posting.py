"""Persist invoice as Authorised and linked to its GL header."""

from __future__ import annotations

from gl.journal.models import GlHeader

from ..models import Invoice, InvoiceStatus


class InvoiceGlAuthorisedLinkPosting:
    """Sets ``posted_gl_header`` and invoice status after the GL voucher exists."""

    def execute(self, *, invoice: Invoice, header: GlHeader) -> None:
        invoice.posted_gl_header = header
        invoice.status = InvoiceStatus.AUTHORISED
        invoice.save(update_fields=["posted_gl_header", "status", "updated_on"])
