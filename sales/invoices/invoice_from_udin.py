"""Create a one-line invoice from a single UDIN (bulk / automation)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from gl.fiscal_years.models import FiscalYear
from sales.udins.models import Udin
from sales.udins.service_fy_build import normalize_service_fy

from .forms import persist_maps_and_lines
from .invoice_lines import (
    build_invoice_lines_from_map_entries,
    gross_from_lines,
    money2,
    taxes_total_from_lines,
)
from .invoice_numbers import next_invoice_no
from .models import InvUdinMap, Invoice
from .udin_map_sync import sync_udin_flags_for_pks


def fiscal_year_for_udin_service_fy(udin: Udin) -> FiscalYear | None:
    raw = (udin.ay_fy or "").strip().upper()
    if not raw:
        return None
    code = raw[:4] if len(raw) >= 4 else raw
    return FiscalYear.objects.filter(fy_no__iexact=code).first()


def line_description_for_udin(udin: Udin) -> str:
    return (udin.service.service_desc or "").strip() if udin.service_id else ""


def invoice_readiness_issues(
    *,
    client_id: int | None,
    service_id: int | None,
    ay_fy: str,
    inv_tv_amount: Decimal | None,
    is_invoiced: bool = False,
    udin_pk: int | None = None,
) -> list[str]:
    issues: list[str] = []
    if not client_id:
        issues.append("Set Client.")
    if not service_id:
        issues.append("Set Service.")
    if is_invoiced:
        issues.append("Already invoiced.")
    elif udin_pk and InvUdinMap.objects.filter(udin_id=udin_pk).exists():
        issues.append("Linked to an invoice map.")
    if inv_tv_amount is None:
        issues.append("Set Inv TV amt.")
    elif inv_tv_amount < 0:
        issues.append("Inv TV amt cannot be negative.")
    code = normalize_service_fy(ay_fy or "")
    if not code:
        issues.append("Service FY must be FY26, FY27, etc.")
    elif not FiscalYear.objects.filter(fy_no__iexact=code).exists():
        issues.append(f"No Fiscal Year master row matches {code}.")
    return issues


def validate_udin_ready_for_invoice(udin: Udin) -> str | None:
    issues = invoice_readiness_issues(
        client_id=udin.client_id,
        service_id=udin.service_id,
        ay_fy=udin.ay_fy or "",
        inv_tv_amount=udin.inv_tv_amount,
        is_invoiced=udin.is_invoiced,
        udin_pk=udin.pk,
    )
    return issues[0] if issues else None


def inv_tv_amount_from_form_value(raw) -> Decimal | None:
    text = (raw if raw is not None else "")
    if hasattr(text, "strip"):
        text = text.strip()
    else:
        text = str(text).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def create_invoice_from_udin(*, user, udin: Udin) -> tuple[Invoice | None, str | None]:
    """
    Create one invoice with a single UDIN line. Returns (invoice, None) or (None, error_message).
    Caller should wrap in transaction.atomic() if grouping with other writes.
    """
    err = validate_udin_ready_for_invoice(udin)
    if err:
        return None, err
    fy = fiscal_year_for_udin_service_fy(udin)
    assert fy is not None
    invoice_date = udin.inv_date or timezone.localdate()
    service_desc = line_description_for_udin(udin)
    map_rows = [(udin, service_desc, money2(Decimal(str(udin.inv_tv_amount))))]
    tax_type = udin.client.invoice_tax_type
    entries = [{"line_amount": r[2], "service_desc": r[1]} for r in map_rows]
    lines = build_invoice_lines_from_map_entries(
        map_entries=entries,
        invoice_tax_type=tax_type,
    )
    tv = money2(sum(r[2] for r in map_rows))
    tax_tot = taxes_total_from_lines(lines)
    gross = gross_from_lines(lines, tv)
    invoice_no = next_invoice_no(client=udin.client, invoice_date=invoice_date)
    with transaction.atomic():
        inv = Invoice(
            client=udin.client,
            service=udin.service,
            fiscal_year=fy,
            invoice_date=invoice_date,
            invoice_no=invoice_no,
            inv_taxable_value=tv,
            taxes=tax_tot,
            inv_gross=gross,
            narration="",
            created_by=user,
        )
        inv.save()
        persist_maps_and_lines(invoice=inv, map_rows=map_rows, invoice_tax_type=tax_type)
        sync_udin_flags_for_pks({udin.pk}, invoice=inv)
    return inv, None
