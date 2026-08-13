"""
Cumulative GL snapshots: ``tb_table`` (FY + account) and ``tb_table_month`` (FY + month + account).

- **Incremental:** :func:`apply_tb_delta_for_gl_header` updates both tables for each line of
  an **Authorised** header (posting date ``tran_date``). Month bucket uses the **calendar
  month** of ``tran_date`` (``period_from`` … ``period_to``).
- **Rebuild:** :func:`rebuild_tb_table_from_gl_lines` and :func:`rebuild_tb_table_month_from_gl_lines`.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction

from gl.fiscal_years.models import FiscalYear

from .models import GlHeader, GlLine, TbTable, TbTableMonth, gl_amount_rounded


def calendar_month_bounds(tran_date: date) -> tuple[date, date]:
    """First and last calendar day of the month containing ``tran_date``."""
    y, m = tran_date.year, tran_date.month
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last_day)


def fiscal_year_for_tran_date(tran_date):
    """Fiscal year whose date range contains ``tran_date`` (latest ``fy_no`` if overlapping)."""
    return (
        FiscalYear.objects.filter(
            start_date__lte=tran_date,
            end_date__gte=tran_date,
        )
        .order_by("-fy_no")
        .first()
    )


def apply_tb_delta_for_gl_header(header: GlHeader) -> None:
    """
    Add this voucher's line amounts into ``tb_table`` for the header's fiscal year.

    No-op if the header is not Authorised or no fiscal year matches ``tran_date``.
    """
    if header.status != GlHeader.Status.AUTHORISED:
        return
    fy = fiscal_year_for_tran_date(header.tran_date)
    if fy is None:
        return
    with transaction.atomic():
        for line in header.lines.order_by("line_no"):
            amt = gl_amount_rounded(line.amount)
            acct = line.account_id
            row = (
                TbTable.objects.select_for_update()
                .filter(fiscal_year=fy, account_code=acct)
                .first()
            )
            if row is None:
                TbTable.objects.create(
                    fiscal_year=fy, account_code=acct, amount=amt
                )
            else:
                row.amount = gl_amount_rounded(row.amount + amt)
                row.save(update_fields=["amount", "updated_on"])

            p_start, p_end = calendar_month_bounds(header.tran_date)
            mrow = (
                TbTableMonth.objects.select_for_update()
                .filter(
                    fiscal_year=fy,
                    period_from=p_start,
                    account_code=acct,
                )
                .first()
            )
            if mrow is None:
                TbTableMonth.objects.create(
                    fiscal_year=fy,
                    period_from=p_start,
                    period_to=p_end,
                    account_code=acct,
                    amount=amt,
                )
            else:
                mrow.amount = gl_amount_rounded(mrow.amount + amt)
                mrow.period_to = p_end
                mrow.save(update_fields=["amount", "period_to", "updated_on"])


def rebuild_tb_table_from_gl_lines() -> int:
    """
    Delete all ``tb_table`` rows and repopulate from every line on Authorised headers.

    Returns the number of ``tb_table`` rows created.
    """
    buckets: dict[tuple[int, str], Decimal] = {}
    for line in (
        GlLine.objects.filter(header__status=GlHeader.Status.AUTHORISED)
        .select_related("header")
        .order_by("header_id", "line_no")
    ):
        hdr = line.header
        fy = fiscal_year_for_tran_date(hdr.tran_date)
        if fy is None:
            continue
        key = (fy.pk, line.account_id)
        buckets[key] = buckets.get(key, Decimal("0")) + gl_amount_rounded(line.amount)

    with transaction.atomic():
        TbTable.objects.all().delete()
        rows = [
            TbTable(
                fiscal_year_id=fy_id,
                account_code=code,
                amount=gl_amount_rounded(total),
            )
            for (fy_id, code), total in buckets.items()
        ]
        TbTable.objects.bulk_create(rows)
    return len(rows)


def rebuild_tb_table_month_from_gl_lines() -> int:
    """
    Delete all ``tb_table_month`` rows and repopulate from every line on Authorised headers.

    Returns the number of ``tb_table_month`` rows created.
    """
    buckets: dict[tuple[int, date, str], Decimal] = {}
    for line in (
        GlLine.objects.filter(header__status=GlHeader.Status.AUTHORISED)
        .select_related("header")
        .order_by("header_id", "line_no")
    ):
        hdr = line.header
        fy = fiscal_year_for_tran_date(hdr.tran_date)
        if fy is None:
            continue
        p_start, _p_end = calendar_month_bounds(hdr.tran_date)
        key = (fy.pk, p_start, line.account_id)
        buckets[key] = buckets.get(key, Decimal("0")) + gl_amount_rounded(line.amount)

    with transaction.atomic():
        TbTableMonth.objects.all().delete()
        rows = []
        for (fy_id, p_start, code), total in buckets.items():
            _, p_end = calendar_month_bounds(p_start)
            rows.append(
                TbTableMonth(
                    fiscal_year_id=fy_id,
                    period_from=p_start,
                    period_to=p_end,
                    account_code=code,
                    amount=gl_amount_rounded(total),
                )
            )
        TbTableMonth.objects.bulk_create(rows)
    return len(rows)
