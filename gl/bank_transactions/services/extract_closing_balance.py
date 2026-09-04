"""Best-effort closing balance extraction from a bank statement PDF.

Two strategies, tried in order:

1. Label-based: a line containing a 'closing balance' style label with an
   amount on it (works well for single-month statements).
2. Transaction-scan: for a given ``ym`` (e.g. 'M2601' = Jan 2026), scan every
   dated transaction line, keep the ones falling in that month, and take the
   last dated line's trailing amount (the running/closing balance column).
   Lets one annual statement be uploaded once per row/month.

   Statements often carry two dates per line (Transaction Date and Value
   Date). Month-matching always uses the Value Date, since that's what the
   bank books the balance against. Column order (which date comes first)
   varies by bank, so it's detected once from the statement's own header
   row rather than assumed.

Statement formats vary a lot by bank, so this is heuristic: if nothing
confident is found, ``None`` is returned and the caller should ask for
manual entry.
"""

from __future__ import annotations

import re
from datetime import date

from pypdf import PdfReader

_LABEL_RE = re.compile(
    r"(closing\s*bal(?:ance)?|end(?:ing)?\s*bal(?:ance)?|available\s*bal(?:ance)?)",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r"[\d][\d,]*\.\d{2}")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# DD/MM/YYYY, DD-MM-YYYY, DD/MM/YY, DD-MM-YY
_DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})\b")
# DD MMM YYYY, DD-MMM-YYYY (e.g. 01 Apr 2024, 01-Apr-2024)
_DATE_MONNAME_RE = re.compile(
    r"\b(\d{1,2})[\s-]([A-Za-z]{3})[\s-](\d{2}|\d{4})\b"
)

_HEADER_VALUE_DATE_RE = re.compile(r"value\s*d(?:at)?e?", re.IGNORECASE)
_HEADER_PLAIN_DATE_RE = re.compile(r"\bd(?:at)?e\b", re.IGNORECASE)


def _extract_text(file_obj) -> str:
    reader = PdfReader(file_obj)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _full_year(yy: int) -> int:
    return 2000 + yy if yy < 100 else yy


def _parse_date_match(kind: str, groups: tuple[str, ...]) -> date | None:
    if kind == "numeric":
        d, mo, y = groups
        try:
            return date(_full_year(int(y)), int(mo), int(d))
        except ValueError:
            return None
    d, mon_name, y = groups
    mo = _MONTHS.get(mon_name.lower()[:3])
    if not mo:
        return None
    try:
        return date(_full_year(int(y)), mo, int(d))
    except ValueError:
        return None


def _all_dates_in_line(line: str) -> list[date]:
    """Every date found on the line, left-to-right in the order they appear."""
    matches = []
    for m in _DATE_NUMERIC_RE.finditer(line):
        matches.append((m.start(), "numeric", m.groups()))
    for m in _DATE_MONNAME_RE.finditer(line):
        matches.append((m.start(), "monname", m.groups()))
    matches.sort(key=lambda item: item[0])

    dates = []
    for _, kind, groups in matches:
        parsed = _parse_date_match(kind, groups)
        if parsed is not None:
            dates.append(parsed)
    return dates


def _value_date_position(text: str) -> str:
    """
    Whether the Value Date is the 'first' or 'second' date column, detected
    from the statement's own header row (e.g. "Txn Date Value Dt ..." vs
    "Value Date Txn Date ..."). Defaults to 'second' (the common layout)
    if no header line can be identified.
    """
    for line in text.splitlines()[:40]:
        vm = _HEADER_VALUE_DATE_RE.search(line)
        if not vm:
            continue
        before = line[: vm.start()]
        after = line[vm.end():]
        if _HEADER_PLAIN_DATE_RE.search(before):
            return "second"
        if _HEADER_PLAIN_DATE_RE.search(after):
            return "first"
    return "second"


def _line_value_date(line: str, value_date_position: str) -> date | None:
    dates = _all_dates_in_line(line)
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0]
    return dates[1] if value_date_position == "second" else dates[0]


def _closing_balance_by_label(text: str) -> float | None:
    best: float | None = None
    for line in text.splitlines():
        if not _LABEL_RE.search(line):
            continue
        amounts = _AMOUNT_RE.findall(line)
        if not amounts:
            continue
        try:
            best = float(amounts[-1].replace(",", ""))
        except ValueError:
            continue
    return best


def _closing_balance_for_month(text: str, ym: str) -> float | None:
    """Last value-dated transaction line's trailing amount, for the given ``ym`` (MYYMM)."""
    if not ym or len(ym) != 5 or ym[0] != "M" or not ym[1:].isdigit():
        return None
    target_year = _full_year(int(ym[1:3]))
    target_month = int(ym[3:5])

    value_date_position = _value_date_position(text)

    best_date: date | None = None
    best_amount: float | None = None

    for line in text.splitlines():
        line_date = _line_value_date(line, value_date_position)
        if line_date is None:
            continue
        if line_date.year != target_year or line_date.month != target_month:
            continue
        amounts = _AMOUNT_RE.findall(line)
        if not amounts:
            continue
        try:
            amount = float(amounts[-1].replace(",", ""))
        except ValueError:
            continue
        if best_date is None or line_date >= best_date:
            best_date = line_date
            best_amount = amount

    return best_amount


def extract_closing_balance(file_obj, *, ym: str | None = None) -> float | None:
    """
    Return a confidently-matched closing balance amount for the PDF, or
    ``None`` if nothing matched.

    If ``ym`` is given, prefers the last transaction value-dated in that
    month; falls back to a 'closing balance' label match if that fails (or
    if ``ym`` wasn't given at all).
    """
    text = _extract_text(file_obj)
    if not text:
        return None

    if ym:
        amount = _closing_balance_for_month(text, ym)
        if amount is not None:
            return amount

    return _closing_balance_by_label(text)


def extract_closing_balances_for_months(file_obj, yms: list[str]) -> dict[str, float]:
    """
    For a statement covering many months, return {ym: closing_balance} for
    every ``ym`` it could confidently match (transaction-scan only; the
    single 'closing balance' label isn't meaningful across several months).

    Months with no dated transactions at all (dormant months) don't get a
    line to scan, so their balance is carried forward unchanged from the
    nearest earlier month that did have one. ``yms`` must be in
    chronological order for this to work. Months before the first month with
    any match are left absent (nothing to carry forward from).
    """
    text = _extract_text(file_obj)
    if not text:
        return {}

    found: dict[str, float] = {}
    for ym in yms:
        amount = _closing_balance_for_month(text, ym)
        if amount is not None:
            found[ym] = amount

    results: dict[str, float] = {}
    last_known: float | None = None
    for ym in yms:
        if ym in found:
            last_known = found[ym]
            results[ym] = found[ym]
        elif last_known is not None:
            results[ym] = last_known
    return results
