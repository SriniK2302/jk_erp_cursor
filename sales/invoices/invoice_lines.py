"""Default GST / IGST invoice lines from taxable value and client invoice tax type."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sales.clients.models import Client

LINE_SERVICE = "Service"
LINE_CGST = "CGST"
LINE_SGST = "SGST"
LINE_IGST = "IGST"

TAX_LINE_TYPES = frozenset({LINE_CGST, LINE_SGST, LINE_IGST})


def money2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_default_invoice_lines(
    *,
    taxable_value: Decimal,
    invoice_tax_type: str,
) -> list[dict]:
    """
    Return line dicts: line_no, line_type, line_base_amount, percentage, item_amount.

    Service: 100% of taxable, item = taxable.
    GST (intra-state): CGST 9% and SGST 9% of taxable each.
    IGST (inter-state): IGST 18% of taxable.
    """
    tv = money2(Decimal(str(taxable_value)))
    lines: list[dict] = [
        {
            "line_no": 1,
            "line_type": LINE_SERVICE,
            "line_base_amount": tv,
            "percentage": Decimal("100"),
            "item_amount": tv,
        }
    ]
    if invoice_tax_type == Client.INVOICE_TAX_IGST:
        pct = Decimal("18")
        item = money2(tv * pct / Decimal("100"))
        lines.append(
            {
                "line_no": 2,
                "line_type": LINE_IGST,
                "line_base_amount": tv,
                "percentage": pct,
                "item_amount": item,
            }
        )
    else:
        pct = Decimal("9")
        half = money2(tv * pct / Decimal("100"))
        lines.append(
            {
                "line_no": 2,
                "line_type": LINE_CGST,
                "line_base_amount": tv,
                "percentage": pct,
                "item_amount": half,
            }
        )
        lines.append(
            {
                "line_no": 3,
                "line_type": LINE_SGST,
                "line_base_amount": tv,
                "percentage": pct,
                "item_amount": half,
            }
        )
    return lines


def build_invoice_lines_from_map_entries(
    *,
    map_entries: list[dict],
    invoice_tax_type: str,
) -> list[dict]:
    """
    One Service line per map entry (line_no 1..k), then IGST or CGST+SGST on total taxable.

    Each map entry: ``line_amount`` (Decimal), ``service_desc`` (optional str) → ``line_description`` on Service rows.
    """
    rows = [
        {
            "line_amount": money2(Decimal(str(e["line_amount"]))),
            "service_desc": (e.get("service_desc") or "").strip(),
        }
        for e in map_entries
        if e.get("line_amount") is not None and money2(Decimal(str(e["line_amount"]))) >= 0
    ]
    if not rows:
        return []
    lines: list[dict] = []
    for i, row in enumerate(rows, start=1):
        amt = row["line_amount"]
        lines.append(
            {
                "line_no": i,
                "line_type": LINE_SERVICE,
                "line_base_amount": amt,
                "percentage": Decimal("100"),
                "item_amount": amt,
                "line_description": row["service_desc"],
            }
        )
    tv_total = money2(sum(r["line_amount"] for r in rows))
    n = len(lines)
    if invoice_tax_type == Client.INVOICE_TAX_IGST:
        pct = Decimal("18")
        item = money2(tv_total * pct / Decimal("100"))
        lines.append(
            {
                "line_no": n + 1,
                "line_type": LINE_IGST,
                "line_base_amount": tv_total,
                "percentage": pct,
                "item_amount": item,
                "line_description": "",
            }
        )
    else:
        pct = Decimal("9")
        half = money2(tv_total * pct / Decimal("100"))
        lines.append(
            {
                "line_no": n + 1,
                "line_type": LINE_CGST,
                "line_base_amount": tv_total,
                "percentage": pct,
                "item_amount": half,
                "line_description": "",
            }
        )
        lines.append(
            {
                "line_no": n + 2,
                "line_type": LINE_SGST,
                "line_base_amount": tv_total,
                "percentage": pct,
                "item_amount": half,
                "line_description": "",
            }
        )
    return lines


def taxes_total_from_lines(lines: list[dict]) -> Decimal:
    total = Decimal("0")
    for r in lines:
        if r["line_type"] in TAX_LINE_TYPES:
            total += money2(Decimal(str(r["item_amount"])))
    return money2(total)


def gross_from_lines(lines: list[dict], taxable: Decimal) -> Decimal:
    return money2(money2(Decimal(str(taxable))) + taxes_total_from_lines(lines))


def line_dicts_from_models(lines_qs) -> list[dict]:
    out = []
    for row in lines_qs:
        out.append(
            {
                "line_no": row.line_no,
                "line_type": row.line_type,
                "line_base_amount": money2(row.line_base_amount),
                "percentage": row.percentage,
                "item_amount": money2(row.item_amount),
                "line_description": getattr(row, "line_description", None) or "",
            }
        )
    return out

