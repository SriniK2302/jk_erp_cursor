from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


def _format_ym(year: int, month: int) -> str:
    return f"M{year % 100:02d}{month:02d}"


def calendar_months_in_fiscal_year(fy) -> list[dict]:
    """Each calendar month overlapping ``fy`` as first-of-month date, label, and ym key."""
    months = []
    cur = date(fy.start_date.year, fy.start_date.month, 1)
    while cur <= fy.end_date:
        months.append(
            {
                "period_from": cur,
                "label": cur.strftime("%b %Y"),
                "ym": _format_ym(cur.year, cur.month),
            }
        )
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


@dataclass
class AccountSummaryReport:
    source_ac: str
    months: list[dict]
    total_debit: float
    total_credit: float


def build_summary_report(
    fy,
    *,
    SourceBankCashAc,
    BankTransactionSourceSummary,
) -> list[AccountSummaryReport]:
    """
    All accounts x all calendar months in ``fy``.

    Each account gets one row per month in the FY; months with no
    ``BankTransactionSourceSummary`` row show as blank (no data built yet).
    """
    months = calendar_months_in_fiscal_year(fy)
    ym_keys = [m["ym"] for m in months]

    accounts = list(SourceBankCashAc.objects.all())
    rows_by_account: dict[str, dict[str, object]] = {}
    for row in BankTransactionSourceSummary.objects.filter(
        source_ac__in=accounts, ym__in=ym_keys
    ).select_related("source_ac", "statement_upload"):
        
        rows_by_account.setdefault(row.source_ac_id, {})[row.ym] = row

    report: list[AccountSummaryReport] = []
    for account in accounts:
        ac = account.source_ac
        existing = rows_by_account.get(ac, {})
        month_rows = []
        total_debit = 0.0
        total_credit = 0.0
        for m in months:
            row = existing.get(m["ym"])
            if row is not None:
                debit = row.debit or 0.0
                credit = row.credit or 0.0
                total_debit += debit
                total_credit += credit
                month_rows.append(
                    {
                        "pk": row.pk,
                        "label": m["label"],
                        "ob": row.ob,
                        "debit": row.debit,
                        "credit": row.credit,
                        "cb": row.cb,
                        "cb_from_statement": row.cb_from_statement,
                        "check_diff": round(row.check_diff, 2) if row.check_diff is not None else None,
                        "statement_file_url": row.statement_upload.statement_file.url if row.statement_upload else None,
                        "statement_file_name": row.statement_upload.statement_file.name.rsplit("/", 1)[-1] if row.statement_upload else None,
                        "has_data": True,
                    }
                )
            else:
                month_rows.append(
                    {
                        "pk": None,
                        "label": m["label"],
                        "ob": None,
                        "debit": None,
                        "credit": None,
                        "cb": None,
                        "cb_from_statement": None,
                        "check_diff": None,
                        "has_data": False,
                    }
                )
        report.append(
            AccountSummaryReport(
                source_ac=ac,
                months=month_rows,
                total_debit=total_debit,
                total_credit=total_credit,
            )
        )
    return report

