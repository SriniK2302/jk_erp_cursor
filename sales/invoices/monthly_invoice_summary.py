"""Monthly invoice summary — one row per calendar month in a fiscal year."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Prefetch

from .gstr1_invoice_list import iter_month_starts_in_fy
from .invoice_lines import LINE_CGST, LINE_IGST, LINE_SERVICE, LINE_SGST, money2
from .models import Invoice, InvoiceLine
from .sales_ledger_tb import _invoice_qs_for_status


def _empty_bucket() -> dict:
    return {
        "invoice_count": 0,
        "taxable_value": Decimal("0"),
        "cgst": Decimal("0"),
        "sgst": Decimal("0"),
        "igst": Decimal("0"),
        "inv_gross": Decimal("0"),
    }


def compute_monthly_invoice_summary(fy, *, invoice_status: str) -> tuple[list[dict], dict]:
    """
    Aggregate invoices by calendar month within the FY (invoice_date).
    Returns (month rows in FY order, FY total row).
    """
    inv_qs = (
        Invoice.objects.filter(
            invoice_date__gte=fy.start_date,
            invoice_date__lte=fy.end_date,
        )
        .prefetch_related(
            Prefetch(
                "invoice_lines",
                queryset=InvoiceLine.objects.order_by("line_no"),
            )
        )
    )
    inv_qs = _invoice_qs_for_status(inv_qs, invoice_status)

    buckets: dict[tuple[int, int], dict] = {}
    for inv in inv_qs:
        if not inv.invoice_date:
            continue
        key = (inv.invoice_date.year, inv.invoice_date.month)
        bucket = buckets.setdefault(key, _empty_bucket())
        bucket["invoice_count"] += 1
        for ln in inv.invoice_lines.all():
            lt = (ln.line_type or "").strip()
            amt = Decimal(str(ln.item_amount or 0))
            if lt == LINE_SERVICE:
                bucket["taxable_value"] += amt
            elif lt == LINE_CGST:
                bucket["cgst"] += amt
            elif lt == LINE_SGST:
                bucket["sgst"] += amt
            elif lt == LINE_IGST:
                bucket["igst"] += amt
        bucket["inv_gross"] += Decimal(str(inv.inv_gross or 0))

    month_rows: list[dict] = []
    fy_total = _empty_bucket()
    for month_first in iter_month_starts_in_fy(fy):
        raw = buckets.get((month_first.year, month_first.month), _empty_bucket())
        row = {
            "month_label": month_first.strftime("%b %Y"),
            "month_first": month_first,
            "invoice_count": raw["invoice_count"],
            "taxable_value": money2(raw["taxable_value"]),
            "cgst": money2(raw["cgst"]),
            "sgst": money2(raw["sgst"]),
            "igst": money2(raw["igst"]),
            "inv_gross": money2(raw["inv_gross"]),
        }
        month_rows.append(row)
        fy_total["invoice_count"] += raw["invoice_count"]
        fy_total["taxable_value"] += raw["taxable_value"]
        fy_total["cgst"] += raw["cgst"]
        fy_total["sgst"] += raw["sgst"]
        fy_total["igst"] += raw["igst"]
        fy_total["inv_gross"] += raw["inv_gross"]

    total_row = {
        "month_label": f"FY total ({fy.fy_no})",
        "invoice_count": fy_total["invoice_count"],
        "taxable_value": money2(fy_total["taxable_value"]),
        "cgst": money2(fy_total["cgst"]),
        "sgst": money2(fy_total["sgst"]),
        "igst": money2(fy_total["igst"]),
        "inv_gross": money2(fy_total["inv_gross"]),
    }
    return month_rows, total_row
