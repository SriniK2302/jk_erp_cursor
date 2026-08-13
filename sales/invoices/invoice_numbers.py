"""Suggested invoice numbers: ``FYxx-CCCC-nnn`` (FY from invoice date, client code, per-client FY serial)."""

from __future__ import annotations

from datetime import date

from gl.fiscal_years.fy_calendar import fy_no_from_calendar_date

from sales.clients.models import Client

from .models import Invoice


def fy_window_for_date(d: date) -> tuple[date, date]:
    """April–March window containing ``d`` (same convention as :func:`fy_no_from_calendar_date`)."""
    if d.month >= 4:
        return date(d.year, 4, 1), date(d.year + 1, 3, 31)
    return date(d.year - 1, 4, 1), date(d.year, 3, 31)


def next_invoice_no(
    *,
    client: Client,
    invoice_date: date,
    exclude_invoice_id: int | None = None,
) -> str:
    """
    Next ``FY27-SVSM-001``-style number: FY from ``invoice_date``, 4-char ``client.client_code``,
    zero-padded serial = 1 + count of this client's invoices in that FY window.
    """
    fy = fy_no_from_calendar_date(invoice_date)
    start, end = fy_window_for_date(invoice_date)
    qs = Invoice.objects.filter(
        client_id=client.pk,
        invoice_date__gte=start,
        invoice_date__lte=end,
    )
    if exclude_invoice_id is not None:
        qs = qs.exclude(pk=exclude_invoice_id)
    serial = qs.count() + 1
    code = (client.client_code or "").strip().upper()
    return f"{fy}-{code}-{serial:03d}"
