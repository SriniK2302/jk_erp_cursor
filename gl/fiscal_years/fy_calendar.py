"""Indian April–March fiscal year helpers (calendar date ↔ ``FYxx`` label)."""

from __future__ import annotations

from datetime import date


def fy_no_from_calendar_date(d: date) -> str:
    """
    Return the ``FYxx`` label for the fiscal year window that contains ``d``.

    Windows are April (year N) through March (year N+1), labelled by the
    **ending** calendar year's last two digits — same convention as
    :func:`gl.fiscal_years.forms.derive_fy_dates`.

    Examples:
        - 2024-04-01 .. 2025-03-31 → ``FY25``
        - 2025-04-01 .. 2026-03-31 → ``FY26``
    """
    end_year = d.year + 1 if d.month >= 4 else d.year
    return f"FY{end_year % 100:02d}"
