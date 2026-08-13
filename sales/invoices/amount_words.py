"""Indian-style rupee amounts in words (whole rupees only, for invoices)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = (
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
)


def _below_thousand(n: int) -> str:
    if n <= 0:
        return ""
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, r = divmod(n, 10)
        base = _TENS[t]
        return f"{base} {_ONES[r]}".strip() if r else base
    h, r = divmod(n, 100)
    head = f"{_ONES[h]} Hundred"
    if r == 0:
        return head
    return f"{head} {_below_thousand(r)}"


def _join(parts: list[str]) -> str:
    return " ".join(p for p in parts if p).strip()


def rupees_in_words(amount: Decimal | float | str | int) -> str:
    """Return e.g. 'Rupees Three Thousand Five Hundred Forty only' (no paise)."""
    n = int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if n < 0:
        n = -n
        neg = True
    else:
        neg = False
    if n == 0:
        return "Rupees Zero only"

    parts: list[str] = []
    crore, n = divmod(n, 10000000)
    if crore:
        parts.append(_below_thousand(crore) + " Crore")
    lakh, n = divmod(n, 100000)
    if lakh:
        parts.append(_below_thousand(lakh) + " Lakh")
    thousand, n = divmod(n, 1000)
    if thousand:
        parts.append(_below_thousand(thousand) + " Thousand")
    if n:
        parts.append(_below_thousand(n))

    core = _join(parts)
    if neg:
        core = "Negative " + core
    return f"Rupees {core} only"
