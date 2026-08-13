"""Build sales invoice GL line specs and delegate voucher persist to ``gl.journal.posting``."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from config.models import SalesLedgerSettings
from gl.journal.models import GlHeader, gl_amount_rounded
from gl.journal.posting import GlAuthorisedVoucherLineSpec, GlAuthorisedVoucherPosting

from ..invoice_lines import LINE_CGST, LINE_IGST, LINE_SGST, money2
from ..models import Invoice

TRAN_ID_PREFIX = "Sales-"


def ym_from_invoice_date(d) -> str:
    """Reporting month key aligned with existing GL tests (e.g. M 2026 04)."""
    return f"M {d.year} {d.month:02d}"


def _next_sales_tran_id() -> str:
    max_suffix = 0
    for tid in GlHeader.objects.filter(tran_id__startswith=TRAN_ID_PREFIX).values_list(
        "tran_id", flat=True
    ):
        rest = tid[len(TRAN_ID_PREFIX) :]
        if rest.isdigit():
            max_suffix = max(max_suffix, int(rest))
    return f"{TRAN_ID_PREFIX}{max_suffix + 1}"


def _tax_amounts_from_lines(invoice: Invoice) -> dict[str, Decimal]:
    out = {LINE_CGST: Decimal("0"), LINE_SGST: Decimal("0"), LINE_IGST: Decimal("0")}
    for row in (
        invoice.invoice_lines.filter(line_type__in=out)
        .values("line_type")
        .annotate(s=Sum("item_amount"))
    ):
        lt = (row["line_type"] or "").strip()
        if lt in out:
            out[lt] = money2(Decimal(str(row["s"] or 0)))
    return out


def _require_sales_ledger_settings() -> SalesLedgerSettings:
    s = SalesLedgerSettings.get_solo()
    missing: list[str] = []
    if not s.sales_ledger_control_account_id:
        missing.append("Sales ledger control account (receivables)")
    if not s.service_income_account_id:
        missing.append("Service income account (professional fees)")
    if not s.cgst_output_account_id:
        missing.append("CGST output account")
    if not s.sgst_output_account_id:
        missing.append("SGST output account")
    if not s.igst_output_account_id:
        missing.append("IGST output account")
    if missing:
        raise ValidationError(
            "Complete Sales ledger settings before posting: " + " · ".join(missing)
        )
    return s


def _build_voucher_line_specs(
    settings: SalesLedgerSettings, invoice: Invoice, ym: str
) -> list[GlAuthorisedVoucherLineSpec]:
    """Sales-only journal shape; GL persist is delegated to ``GlAuthorisedVoucherPosting``."""
    tv = money2(invoice.inv_taxable_value)
    gross = money2(invoice.inv_gross)
    taxes = _tax_amounts_from_lines(invoice)
    tax_total = money2(taxes[LINE_CGST] + taxes[LINE_SGST] + taxes[LINE_IGST])
    if money2(tv + tax_total) != gross:
        raise ValidationError(
            f"Invoice {invoice.invoice_no}: inv gross ({gross}) does not equal "
            f"taxable ({tv}) plus tax lines ({tax_total}). Check invoice lines."
        )

    rows: list[tuple] = [
        (
            settings.sales_ledger_control_account,
            gl_amount_rounded(gross),
            "Professional fee receivable",
        ),
        (
            settings.service_income_account,
            gl_amount_rounded(-tv),
            "Professional fees",
        ),
    ]
    if taxes[LINE_CGST] > 0:
        rows.append(
            (settings.cgst_output_account, gl_amount_rounded(-taxes[LINE_CGST]), "CGST")
        )
    if taxes[LINE_SGST] > 0:
        rows.append(
            (settings.sgst_output_account, gl_amount_rounded(-taxes[LINE_SGST]), "SGST")
        )
    if taxes[LINE_IGST] > 0:
        rows.append(
            (settings.igst_output_account, gl_amount_rounded(-taxes[LINE_IGST]), "IGST")
        )

    net = money2(sum(gl_amount_rounded(a[1]) for a in rows))
    if net != Decimal("0"):
        raise ValidationError(
            f"Invoice {invoice.invoice_no}: journal does not balance internally ({net})."
        )

    return [
        GlAuthorisedVoucherLineSpec(
            account=account,
            amount=amount,
            line_description=desc,
            ym=ym,
            rm_or=ym,
            value_ym=ym,
        )
        for account, amount, desc in rows
    ]


class SalesGlJournalPosting:
    """Maps invoice + sales ledger settings → GL line specs; GL module writes the voucher."""

    def __init__(self) -> None:
        self._gl_voucher = GlAuthorisedVoucherPosting()

    def execute(self, *, invoice: Invoice, user) -> GlHeader:
        settings = _require_sales_ledger_settings()
        ym = ym_from_invoice_date(invoice.invoice_date)
        line_specs = _build_voucher_line_specs(settings, invoice, ym)
        narration = f"Sales Ledger posting for inv no. {invoice.invoice_no}"
        return self._gl_voucher.execute(
            tran_date=invoice.invoice_date,
            tran_id=_next_sales_tran_id(),
            source=GlHeader.Source.SALES,
            narration=narration,
            header_ym=ym,
            line_specs=line_specs,
            created_by=user,
        )
