"""Fill blank YM values on bank_transactions_source from value_date.

Format: 'M' + last 2 digits of year + 2-digit month, e.g. 2026-01-15 -> 'M2601'.

Only rows where ym is currently blank/null are updated. Rows with an existing
ym are left untouched (credit-card statement transactions may legitimately
span months and are assigned ym manually).
"""

from __future__ import annotations

from dataclasses import dataclass


def _ym_from_date(value_date) -> str:
    yy = value_date.year % 100
    return f"M{yy:02d}{value_date.month:02d}"


@dataclass
class BuildYmReport:
    scanned_count: int = 0
    updated_count: int = 0


def build_ym(*, BankTransactionSource) -> BuildYmReport:
    report = BuildYmReport()

    blank_rows = BankTransactionSource.objects.filter(ym__isnull=True) | (
        BankTransactionSource.objects.filter(ym="")
    )
    blank_rows = blank_rows.distinct()

    for txn in blank_rows:
        report.scanned_count += 1
        txn.ym = _ym_from_date(txn.value_date)
        txn.save(update_fields=["ym"])
        report.updated_count += 1

    return report

