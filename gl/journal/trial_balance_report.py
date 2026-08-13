"""
GL Trial Balance by fiscal year and **posting date** (``GlHeader.tran_date``).

* If the FY has **any** Authorised lines with ``tran_date`` in the FY window, the report
  is **period-only** for that window (all account types, one row per account with activity).
* If there are **no** lines in that window (e.g. FY28 before any postings), the report is
  **opening / brought forward**: ``tran_date`` strictly before the FY start — show **Asset**
  and **Liability** accounts; net **Income** and **Expenses** are rolled into a single
  **Retained Earnings** line.

Positive net → Debit column; negative net → Credit column.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from config.models import ChartOfAccount

from .models import GlHeader, GlLine, gl_amount_rounded


def _sum_by_account(qs) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in qs.values("account_id").annotate(s=Sum("amount")):
        code = row["account_id"] or ""
        if not code:
            continue
        out[code] = gl_amount_rounded(Decimal(str(row["s"] or 0)))
    return dict(out)


def _authorised_lines():
    return GlLine.objects.filter(header__status=GlHeader.Status.AUTHORISED).select_related(
        "header"
    )


def build_gl_trial_balance_rows(fy) -> tuple[list[dict], Decimal, Decimal]:
    """
    Return ``(rows, total_debits, total_credits)`` for the selected fiscal year.

    Each row: ``account_name``, ``account_code``, ``debit`` (Decimal|None), ``credit`` (Decimal|None).
    """
    start, end = fy.start_date, fy.end_date

    period_qs = _authorised_lines().filter(
        header__tran_date__gte=start,
        header__tran_date__lte=end,
    )
    period_by = _sum_by_account(period_qs)
    has_period = any(v != 0 for v in period_by.values())

    if has_period:
        combined = period_by
        use_opening_mode = False
    else:
        opening_qs = _authorised_lines().filter(header__tran_date__lt=start)
        combined = _sum_by_account(opening_qs)
        use_opening_mode = True

    codes = [c for c, v in combined.items() if v != 0]
    coa_map = {
        c.account_code: c
        for c in ChartOfAccount.objects.filter(account_code__in=codes)
    }

    rows: list[dict] = []
    total_dr = Decimal("0")
    total_cr = Decimal("0")

    def add_row(*, name: str, code: str, amt: Decimal) -> None:
        nonlocal total_dr, total_cr
        if amt == 0:
            return
        if amt > 0:
            rows.append(
                {
                    "account_name": name,
                    "account_code": code,
                    "debit": amt,
                    "credit": None,
                }
            )
            total_dr += amt
        else:
            rows.append(
                {
                    "account_name": name,
                    "account_code": code,
                    "debit": None,
                    "credit": -amt,
                }
            )
            total_cr += -amt

    if not use_opening_mode:
        for code in sorted(combined.keys()):
            amt = combined[code]
            if amt == 0:
                continue
            coa = coa_map.get(code)
            name = (coa.account_name if coa else "Unmapped account").strip()
            add_row(name=name, code=code, amt=amt)
        return rows, total_dr, total_cr

    # Opening mode: BS lines + single Retained Earnings for all PL net
    pl_net = Decimal("0")
    bs_codes: list[tuple[str, Decimal]] = []
    for code, amt in combined.items():
        if amt == 0:
            continue
        coa = coa_map.get(code)
        if coa is None:
            add_row(name="Unmapped account", code=code, amt=amt)
            continue
        if coa.plbs_type in (ChartOfAccount.TYPE_INCOME, ChartOfAccount.TYPE_EXPENSES):
            pl_net = gl_amount_rounded(pl_net + amt)
        elif coa.plbs_type in (ChartOfAccount.TYPE_ASSET, ChartOfAccount.TYPE_LIABILITY):
            bs_codes.append((code, amt))
        else:
            add_row(name=coa.account_name.strip(), code=code, amt=amt)

    for code, amt in sorted(bs_codes, key=lambda x: x[0]):
        coa = coa_map[code]
        add_row(name=coa.account_name.strip(), code=code, amt=amt)

    if pl_net != 0:
        add_row(name="Retained Earnings", code="", amt=pl_net)

    return rows, total_dr, total_cr
