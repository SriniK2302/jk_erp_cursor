from django.conf import settings

from .amount_words import rupees_in_words
from .models import Invoice
from .narration_build import invoice_header_narration_for_display


def preview_narration_one_line(invoice: Invoice) -> str:
    return invoice_header_narration_for_display(invoice)


def preview_line_dicts(invoice: Invoice) -> list[dict]:
    rows = list(invoice.invoice_lines.order_by("line_no"))
    if rows:
        return [
            {
                "line_no": L.line_no,
                "line_type": L.line_type,
                "line_base_amount": L.line_base_amount,
                "percentage": L.percentage,
                "item_amount": L.item_amount,
                "line_description": getattr(L, "line_description", "") or "",
            }
            for L in rows
        ]
    return []


def build_invoice_preview_context(request, invoice: Invoice) -> dict:
    letterhead = getattr(settings, "INVOICE_LETTERHEAD", {})
    udin_maps = list(invoice.inv_udin_maps.all())
    return {
        "invoice": invoice,
        "invoice_udin_maps": udin_maps,
        "preview_lines": preview_line_dicts(invoice),
        "letterhead": letterhead,
        "amount_in_words": rupees_in_words(invoice.inv_gross),
        "narration_one_line": preview_narration_one_line(invoice),
    }
