"""Update YM on bank_transactions_source from value_date.

Format: 'M' + last 2 digits of year + 2-digit month, e.g. 2026-01-15 -> 'M2601'.

Runs as a single bulk UPDATE statement (not one row at a time), so it stays
fast even on large tables. By default only fills rows where ym is blank.
Pass force=True to recalculate every row from its current Value Date — use
this after changing a Value Date (e.g. to align a credit-card transaction
with its statement cycle) so YM picks up the change.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models
from django.db.models import F, Func, Q, Value
from django.db.models.functions import Concat


class _ToChar(Func):
    """PostgreSQL TO_CHAR(value, format) — used to format a date as 'YYMM'."""

    function = "TO_CHAR"
    output_field = models.CharField()


def _new_ym_expression():
    return Concat(Value("M"), _ToChar(F("value_date"), Value("YYMM")))


@dataclass
class BuildYmReport:
    scanned_count: int = 0
    updated_count: int = 0


def build_ym(*, BankTransactionSource, force: bool = False) -> BuildYmReport:
    report = BuildYmReport()

    base = BankTransactionSource.objects.filter(value_date__isnull=False)
    if not force:
        base = base.filter(Q(ym__isnull=True) | Q(ym=""))

    report.scanned_count = base.count()
    report.updated_count = base.exclude(ym=_new_ym_expression()).update(
        ym=_new_ym_expression()
    )

    return report
