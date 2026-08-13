"""
Post Fresh invoices to the GL using Setup → Sales ledger COA mappings.

Journal: Dr receivables control (inv gross); Cr service income (inv taxable);
Cr CGST / SGST / IGST output accounts from invoice line amounts.
Header is saved as Authorised immediately. Tran id: Sales-{n} (monotonic counter).

Implementation is split into posting objects under ``posting/``; this module
keeps the public entry points used by views and tests.
"""

from __future__ import annotations

from gl.journal.models import GlHeader

from .models import Invoice
from .posting import SalesInvoiceGlPostOrchestrator
from .posting.sales_gl_journal_posting import TRAN_ID_PREFIX, ym_from_invoice_date

_default_orchestrator = SalesInvoiceGlPostOrchestrator()


def post_fresh_invoice_to_gl(*, invoice: Invoice, user) -> GlHeader:
    """
    Create one Authorised GL voucher for this invoice and mark the invoice Authorised.

    Caller must hold a row lock on the invoice (e.g. select_for_update inside atomic).
    """
    return _default_orchestrator.post_fresh_invoice_to_gl(invoice=invoice, user=user)


def bulk_post_fresh_invoices_to_gl(*, invoice_pks: list[int], user) -> tuple[int, list[str]]:
    """
    Post all given invoices in one transaction (all succeed or none).

    Returns (posted_count, error_messages). On any error, rolls back and returns (0, [msg, ...]).
    """
    return _default_orchestrator.bulk_post_fresh_invoices_to_gl(
        invoice_pks=invoice_pks, user=user
    )


__all__ = [
    "TRAN_ID_PREFIX",
    "bulk_post_fresh_invoices_to_gl",
    "post_fresh_invoice_to_gl",
    "ym_from_invoice_date",
]
