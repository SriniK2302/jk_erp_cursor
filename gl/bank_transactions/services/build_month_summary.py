from __future__ import annotations

from dataclasses import dataclass, field


def _parse_ym(ym: str) -> tuple[int, int]:
    yy = int(ym[1:3])
    mm = int(ym[3:5])
    year = 2000 + yy
    return year, mm


def _format_ym(year: int, month: int) -> str:
    yy = year % 100
    return f"M{yy:02d}{month:02d}"


def _next_ym(ym: str) -> str:
    year, month = _parse_ym(ym)
    if month == 12:
        return _format_ym(year + 1, 1)
    return _format_ym(year, month + 1)


def _is_valid_ym(ym: str | None) -> bool:
    if not ym or len(ym) != 5 or ym[0] != "M" or not ym[1:].isdigit():
        return False
    _, month = _parse_ym(ym)
    return 1 <= month <= 12


@dataclass
class BuildMonthSummaryReport:
    accounts_processed: int = 0
    months_created: int = 0
    months_updated: int = 0
    accounts_needing_ob: list[str] = field(default_factory=list)
    accounts_built_without_ob: list[str] = field(default_factory=list)
    accounts_with_invalid_ym_transactions: list[str] = field(default_factory=list)


def build_month_summary(
    *,
    SourceBankCashAc,
    BankTransactionSource,
    BankTransactionSourceSummary,
    BankTransactionSourceOb,
) -> BuildMonthSummaryReport:
    report = BuildMonthSummaryReport()

    all_accounts = list(SourceBankCashAc.objects.all())
    ob_by_account = {
        ob.source_ac_id: ob
        for ob in BankTransactionSourceOb.objects.all()
    }

    for account in all_accounts:
        ac = account.source_ac
        ob_row = ob_by_account.get(ac)

        txns = BankTransactionSource.objects.filter(source_ac=account)

        monthly: dict[str, dict[str, float]] = {}
        account_type_by_ym: dict[str, str] = {}
        has_invalid_ym = False
        for txn in txns:
            if not _is_valid_ym(txn.ym):
                has_invalid_ym = True
                continue
            bucket = monthly.setdefault(txn.ym, {"debit": 0.0, "credit": 0.0})
            bucket["debit"] += txn.debit or 0.0
            bucket["credit"] += txn.credit or 0.0
            if txn.account_type and txn.ym not in account_type_by_ym:
                account_type_by_ym[txn.ym] = txn.account_type

        if has_invalid_ym:
            report.accounts_with_invalid_ym_transactions.append(ac)

        txn_yms = list(monthly.keys())

        if ob_row is not None and _is_valid_ym(ob_row.ym):
            anchor_ym = ob_row.ym
            running_ob = ob_row.ob or 0.0
        elif txn_yms:
            # No opening balance yet: build anyway from the earliest
            # transaction month with OB treated as 0. Add the OB later and
            # run Build Month Summary again to pick it up.
            anchor_ym = min(txn_yms, key=_parse_ym)
            running_ob = 0.0
            report.accounts_built_without_ob.append(ac)
        else:
            # No OB and no transactions at all: nothing to build.
            report.accounts_needing_ob.append(ac)
            continue

        report.accounts_processed += 1

        last_ym = max([anchor_ym] + txn_yms, key=_parse_ym)

        existing_rows = {
            row.ym: row
            for row in BankTransactionSourceSummary.objects.filter(source_ac=account)
        }
        most_recent_existing_ym = max(existing_rows.keys(), key=_parse_ym) if existing_rows else None

        # If the anchor month's opening balance has changed since it was
        # last built (e.g. OB was just added/corrected), the whole chain of
        # months needs recomputing — a stale OB cascades into every later
        # month's CB. Otherwise, only refresh the most recent month, so
        # earlier months you've already reconciled are left untouched.
        existing_anchor_row = existing_rows.get(anchor_ym)
        force_full_rebuild = (
            existing_anchor_row is not None
            and (existing_anchor_row.ob or 0.0) != running_ob
        )

        ym = anchor_ym
        while True:
            month_totals = monthly.get(ym, {"debit": 0.0, "credit": 0.0})
            debit = month_totals["debit"]
            credit = month_totals["credit"]

            existing = existing_rows.get(ym)
            should_write = (
                existing is None
                or ym == most_recent_existing_ym
                or force_full_rebuild
            )

            if should_write:
                if existing is not None:
                    existing.ob = running_ob
                    existing.debit = debit
                    existing.credit = credit
                    existing.account_type = account_type_by_ym.get(ym, existing.account_type)
                    existing.save(update_fields=["ob", "debit", "credit", "account_type"])
                    report.months_updated += 1
                else:
                    BankTransactionSourceSummary.objects.create(
                        source_ac=account,
                        ym=ym,
                        ob=running_ob,
                        debit=debit,
                        credit=credit,
                        account_type=account_type_by_ym.get(ym),
                    )
                    report.months_created += 1
                running_cb = running_ob + debit - credit
            else:
                running_cb = existing.cb

            running_ob = running_cb

            if ym == last_ym:
                break
            ym = _next_ym(ym)

    return report
