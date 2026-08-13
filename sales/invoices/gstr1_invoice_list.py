"""
GSTR-1 style invoice list: one row per invoice with taxes rolled up from invoice_lines.

Period is driven by **invoice_date** (same spirit as Sales Ledger TB). Within a fiscal
year, pick a calendar month; optional YTD runs from FY start through the end of that month.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch

from .invoice_lines import LINE_CGST, LINE_IGST, LINE_SERVICE, LINE_SGST, money2
from .models import InvUdinMap, Invoice, InvoiceLine
from .narration_build import invoice_header_narration_for_display
from .sales_ledger_tb import _invoice_qs_for_status


def iter_month_starts_in_fy(fy) -> list[date]:
    """First calendar day of each month overlapping the fiscal year (inclusive order)."""
    out: list[date] = []
    cur = date(fy.start_date.year, fy.start_date.month, 1)
    end = fy.end_date
    while cur <= end:
        out.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def fy_month_select_options(fy) -> list[dict[str, str]]:
    """For HTML <select>: value YYYY-MM, label e.g. Apr 2098."""
    opts: list[dict[str, str]] = []
    for d0 in iter_month_starts_in_fy(fy):
        value = d0.isoformat()[:7]
        label = d0.strftime("%b %Y")
        opts.append({"value": value, "label": label})
    return opts


def month_bounds(y: int, m: int) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


@dataclass(frozen=True)
class Gstr1DateWindow:
    date_from: date
    date_to: date
    label: str


def window_for_fy_month(
    fy,
    *,
    month_first: date,
    ytd: bool,
) -> Gstr1DateWindow:
    """``month_first`` must be the first day of a calendar month inside the FY."""
    y, m = month_first.year, month_first.month
    m_start, m_end = month_bounds(y, m)
    m_start = max(m_start, fy.start_date)
    m_end = min(m_end, fy.end_date)
    if ytd:
        d0 = fy.start_date
        d1 = m_end
        label = f"YTD {fy.fy_no} through {m_end.strftime('%b %Y')}"
    else:
        d0 = m_start
        d1 = m_end
        label = f"{m_start.strftime('%b %Y')}"
    return Gstr1DateWindow(date_from=d0, date_to=d1, label=label)


def parse_month_param(raw: str | None, fy) -> date | None:
    """Return first day of month from ``YYYY-MM`` if that month is in the FY month list; else None."""
    if not raw or len(raw) != 7 or raw[4] != "-":
        return None
    try:
        y = int(raw[:4])
        m = int(raw[5:7])
        if m < 1 or m > 12:
            return None
        first = date(y, m, 1)
    except ValueError:
        return None
    allowed = set(iter_month_starts_in_fy(fy))
    if first not in allowed:
        return None
    return first


def default_month_first_for_fy(fy, today: date) -> date:
    months = iter_month_starts_in_fy(fy)
    if not months:
        return fy.start_date
    if fy.start_date <= today <= fy.end_date:
        cur = date(today.year, today.month, 1)
        if cur in months:
            return cur
    return months[0]


def compute_gstr1_invoice_list(
    date_from: date,
    date_to: date,
    *,
    invoice_status: str,
) -> list[dict]:
    """One dict per invoice, line amounts summed by type from invoice_lines."""
    inv_qs = (
        Invoice.objects.filter(invoice_date__gte=date_from, invoice_date__lte=date_to)
        .select_related("client")
        .prefetch_related(
            Prefetch(
                "invoice_lines",
                queryset=InvoiceLine.objects.order_by("line_no"),
            ),
            Prefetch(
                "inv_udin_maps",
                queryset=InvUdinMap.objects.select_related("udin", "udin__service").order_by(
                    "line_no"
                ),
            ),
        )
        .order_by("invoice_date", "invoice_no", "id")
    )
    inv_qs = _invoice_qs_for_status(inv_qs, invoice_status)
    rows: list[dict] = []
    for inv in inv_qs:
        lines = list(inv.invoice_lines.all())
        taxable = Decimal("0")
        cgst = Decimal("0")
        sgst = Decimal("0")
        igst = Decimal("0")
        for ln in lines:
            lt = (ln.line_type or "").strip()
            amt = Decimal(str(ln.item_amount or 0))
            if lt == LINE_SERVICE:
                taxable += amt
            elif lt == LINE_CGST:
                cgst += amt
            elif lt == LINE_SGST:
                sgst += amt
            elif lt == LINE_IGST:
                igst += amt
        rows.append(
            {
                "client_gstn": (inv.client.billing_gstn or "").strip(),
                "client_name": (inv.client.client_name or "").strip(),
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date,
                "narration": invoice_header_narration_for_display(inv),
                "taxable_value": money2(taxable),
                "cgst": money2(cgst),
                "sgst": money2(sgst),
                "igst": money2(igst),
                "inv_gross": money2(Decimal(str(inv.inv_gross or 0))),
            }
        )
    return rows
