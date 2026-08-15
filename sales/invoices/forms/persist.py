from sales.invoices.invoice_lines import build_invoice_lines_from_map_entries
from sales.invoices.models import InvUdinMap, Invoice, InvoiceLine
from sales.invoices.narration_build import header_narration_from_udin_rows


def persist_maps_and_lines(
    *,
    invoice: Invoice,
    map_rows: list,
    invoice_tax_type: str,
) -> None:
    """Replace inv_udin_map and invoice_lines from validated map rows (each: udin, service_desc, line_amount)."""
    InvUdinMap.objects.filter(invoice=invoice).delete()
    entries = []
    for _idx, (udin, service_desc, line_amount) in enumerate(map_rows, start=1):
        InvUdinMap.objects.create(
            invoice=invoice,
            line_no=_idx,
            udin=udin,
            service_desc=service_desc,
            line_amount=line_amount,
        )
        entries.append({"line_amount": line_amount, "service_desc": service_desc})
    lines = build_invoice_lines_from_map_entries(
        map_entries=entries,
        invoice_tax_type=invoice_tax_type,
    )
    InvoiceLine.objects.filter(invoice=invoice).delete()
    for row in lines:
        InvoiceLine.objects.create(
            invoice=invoice,
            line_no=row["line_no"],
            line_type=row["line_type"],
            line_base_amount=row["line_base_amount"],
            percentage=row["percentage"],
            item_amount=row["item_amount"],
            line_description=row.get("line_description") or "",
        )
    if not (invoice.narration or "").strip():
        filled = header_narration_from_udin_rows(map_rows).strip()
        if filled:
            Invoice.objects.filter(pk=invoice.pk).update(narration=filled)
            invoice.narration = filled
