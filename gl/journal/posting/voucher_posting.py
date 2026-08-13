"""Create an Authorised GL header + lines from neutral line specs (any source module)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from django.core.exceptions import ValidationError

from config.models import ChartOfAccount

from ..models import GlHeader, GlLine, gl_amount_rounded


@dataclass(frozen=True)
class GlAuthorisedVoucherLineSpec:
    """One journal leg; amounts use GL convention (debit +, credit −)."""

    account: ChartOfAccount
    amount: Decimal
    line_description: str = ""
    ym: str = ""
    rm_or: str | None = None
    value_ym: str | None = None


class GlAuthorisedVoucherPosting:
    """
    Persists a new GL voucher in **Authorised** state.

    Caller supplies ``tran_id`` (e.g. Sales-1, PO-42), ``source``, narration, and balanced lines.
    Used by Sales, Purchases, Payroll, etc.; domain modules build ``GlAuthorisedVoucherLineSpec`` lists.
    """

    def execute(
        self,
        *,
        tran_date,
        tran_id: str,
        source: str,
        narration: str,
        header_ym: str,
        line_specs: Sequence[GlAuthorisedVoucherLineSpec],
        created_by,
    ) -> GlHeader:
        specs = list(line_specs)
        if not specs:
            raise ValidationError("GL voucher requires at least one line.")
        net = gl_amount_rounded(sum(gl_amount_rounded(s.amount) for s in specs))
        if net != Decimal("0"):
            raise ValidationError(
                f"GL lines do not balance (net {net}); cannot authorise voucher {tran_id!r}."
            )

        hdr = GlHeader.objects.create(
            tran_date=tran_date,
            tran_id=tran_id,
            source=source,
            narration=narration or "",
            ym=header_ym or "",
            line_count=0,
            status=GlHeader.Status.FRESH,
            created_by=created_by,
        )
        for i, spec in enumerate(specs, start=1):
            ym = spec.ym or ""
            rm = spec.rm_or if spec.rm_or is not None else ym
            vym = spec.value_ym if spec.value_ym is not None else ym
            GlLine.objects.create(
                header=hdr,
                line_no=i,
                account=spec.account,
                line_description=spec.line_description or "",
                amount=gl_amount_rounded(spec.amount),
                ym=ym,
                rm_or=rm,
                value_ym=vym,
            )
        hdr.line_count = len(specs)
        hdr.status = GlHeader.Status.AUTHORISED
        hdr.save(update_fields=["line_count", "status", "updated_on"])
        return hdr
