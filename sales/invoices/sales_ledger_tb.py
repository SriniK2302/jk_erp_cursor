"""
On-the-fly Sales Ledger trial balance from invoices (no stored aggregates).

Period: invoices whose **invoice date** falls inside the selected fiscal year’s
``start_date``..``end_date``. **Service FY** on the invoice is not used (MIS).

Opening (b/f): all invoices with **invoice date** strictly before the selected FY
``start_date``. For presentation:
  - **Client** debits = trade receivables (assets) carried forward.
  - **CGST / SGST / IGST** credits = tax liabilities carried forward.
  - **Service** (P&L) cumulative is shown as one line: **Balance carried over from prior years**.

Posting model (v1) per slice:
  Dr  Client = inv_gross
  Cr  Service, CGST, SGST, IGST from invoice lines
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum

from .invoice_lines import LINE_CGST, LINE_IGST, LINE_SERVICE, LINE_SGST
from .invoice_lines import money2
from .models import Invoice, InvoiceLine, InvoiceStatus

# GET / UI values for the Sales Ledger TB status scope
STATUS_SCOPE_ALL = "all"
STATUS_SCOPE_AUTHORISED = "authorised"
STATUS_SCOPE_FRESH = "fresh"
STATUS_SCOPE_CHOICES = (
    STATUS_SCOPE_ALL,
    STATUS_SCOPE_AUTHORISED,
    STATUS_SCOPE_FRESH,
)


def _invoice_qs_for_status(base_qs, invoice_status: str):
    """Restrict queryset by invoice lifecycle status; ``all`` leaves ``base_qs`` unchanged."""
    s = (invoice_status or STATUS_SCOPE_ALL).strip().lower()
    if s == STATUS_SCOPE_AUTHORISED:
        return base_qs.filter(status=InvoiceStatus.AUTHORISED)
    if s == STATUS_SCOPE_FRESH:
        return base_qs.filter(status=InvoiceStatus.FRESH)
    return base_qs

CREDIT_LINE_ORDER = (
    (LINE_SERVICE, "Service (credit)"),
    (LINE_CGST, "CGST (credit)"),
    (LINE_SGST, "SGST (credit)"),
    (LINE_IGST, "IGST (credit)"),
)

TAX_KEYS = (LINE_CGST, LINE_SGST, LINE_IGST)


def _aggregate_for_invoices(invoice_qs) -> dict:
    """Aggregate client debits and credits-by-line-type for the given invoice queryset."""
    empty_credits = {k: Decimal("0") for k, _ in CREDIT_LINE_ORDER}
    if not invoice_qs.exists():
        return {
            "client_rows": [],
            "credit_by_type": empty_credits.copy(),
            "credit_rows_other": [],
            "total_dr": money2(Decimal("0")),
            "total_cr": money2(Decimal("0")),
            "invoice_count": 0,
        }

    client_qs = (
        invoice_qs.values("client_id", "client__client_short_name", "client__client_name")
        .annotate(debit=Sum("inv_gross"), invoice_count=Count("id"))
        .order_by("client__client_short_name")
    )
    client_rows = [
        {
            "name": (row["client__client_short_name"] or row["client__client_name"] or "—").strip(),
            "invoice_count": int(row["invoice_count"] or 0),
            "debit": money2(Decimal(str(row["debit"] or 0))),
        }
        for row in client_qs
    ]

    dr_agg = invoice_qs.aggregate(s=Sum("inv_gross"))
    total_dr = money2(Decimal(str(dr_agg["s"] or 0)))

    line_qs = (
        InvoiceLine.objects.filter(invoice__in=invoice_qs)
        .values("line_type")
        .annotate(cr=Sum("item_amount"))
    )
    remaining: dict[str, Decimal] = {}
    for row in line_qs:
        lt = (row["line_type"] or "").strip()
        remaining[lt] = money2(Decimal(str(row["cr"] or 0)))

    credit_by_type = empty_credits.copy()
    for key, _ in CREDIT_LINE_ORDER:
        credit_by_type[key] = remaining.pop(key, Decimal("0"))

    credit_rows_other: list[dict] = []
    for lt, amt in sorted(remaining.items(), key=lambda x: x[0]):
        if amt == 0:
            continue
        credit_rows_other.append(
            {
                "line_type": lt,
                "label": f"Other — {lt}",
                "credit": amt,
            }
        )

    total_cr = money2(
        sum(credit_by_type.values()) + sum(r["credit"] for r in credit_rows_other)
    )

    return {
        "client_rows": client_rows,
        "credit_by_type": credit_by_type,
        "credit_rows_other": credit_rows_other,
        "total_dr": total_dr,
        "total_cr": total_cr,
        "invoice_count": invoice_qs.count(),
    }


def _opening_display(agg: dict) -> dict:
    """Split P&L (Service) into 'balance carried over' line; keep tax liabilities separate."""
    byt = agg["credit_by_type"]
    service_amt = byt.get(LINE_SERVICE, Decimal("0"))
    tax_rows = []
    for key in TAX_KEYS:
        label = {
            LINE_CGST: "CGST (liability, b/f from prior years)",
            LINE_SGST: "SGST (liability, b/f from prior years)",
            LINE_IGST: "IGST (liability, b/f from prior years)",
        }[key]
        tax_rows.append({"line_type": key, "label": label, "credit": byt.get(key, Decimal("0"))})

    total_cr_open = money2(
        sum(r["credit"] for r in tax_rows) + service_amt + sum(r["credit"] for r in agg["credit_rows_other"])
    )

    return {
        "client_rows": [
            {
                "name": f"{r['name']} (receivable, b/f)",
                "invoice_count": r["invoice_count"],
                "debit": r["debit"],
            }
            for r in agg["client_rows"]
        ],
        "tax_rows": tax_rows,
        "balance_carried_credit": service_amt,
        "balance_carried_label": "Balance carried over from prior years (cumulative service / clearing)",
        "credit_rows_other": agg["credit_rows_other"],
        "total_dr": agg["total_dr"],
        "total_cr": total_cr_open,
        "invoice_count": agg["invoice_count"],
    }


def _period_display(agg: dict) -> dict:
    """Current FY slice: show Service on its own line (period revenue)."""
    byt = agg["credit_by_type"]
    credit_rows_known = []
    for key, label in CREDIT_LINE_ORDER:
        credit_rows_known.append({"line_type": key, "label": label, "credit": byt.get(key, Decimal("0"))})

    return {
        "client_rows": [
            {
                "name": r["name"],
                "invoice_count": r["invoice_count"],
                "debit": r["debit"],
            }
            for r in agg["client_rows"]
        ],
        "credit_rows_known": credit_rows_known,
        "credit_rows_other": agg["credit_rows_other"],
        "total_dr": agg["total_dr"],
        "total_cr": agg["total_cr"],
        "invoice_count": agg["invoice_count"],
    }


def compute_sales_ledger_tb(fy, *, invoice_status: str = STATUS_SCOPE_ALL) -> dict:
    """Opening (b/f) + current-period TB; grand totals must balance when data is consistent.

    ``invoice_status``: ``all`` | ``authorised`` | ``fresh`` — same filter applied to
    opening and period invoice sets.
    """
    start, end = fy.start_date, fy.end_date

    opening_inv = _invoice_qs_for_status(
        Invoice.objects.filter(invoice_date__lt=start), invoice_status
    )
    period_inv = _invoice_qs_for_status(
        Invoice.objects.filter(invoice_date__gte=start, invoice_date__lte=end),
        invoice_status,
    )

    agg_open = _aggregate_for_invoices(opening_inv)
    agg_period = _aggregate_for_invoices(period_inv)

    opening = _opening_display(agg_open)
    period = _period_display(agg_period)

    grand_dr = money2(opening["total_dr"] + period["total_dr"])
    grand_cr = money2(opening["total_cr"] + period["total_cr"])
    diff = money2(abs(grand_dr - grand_cr))
    balanced = diff <= Decimal("0.01")

    return {
        "opening": opening,
        "period": period,
        "grand_total_dr": grand_dr,
        "grand_total_cr": grand_cr,
        "difference": diff,
        "balanced": balanced,
        "opening_invoice_count": opening["invoice_count"],
        "period_invoice_count": period["invoice_count"],
        "invoice_status": (invoice_status or STATUS_SCOPE_ALL).strip().lower(),
    }
