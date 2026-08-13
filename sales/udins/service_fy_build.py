"""Derive and validate UDIN Service FY (``ay_fy``)."""

from __future__ import annotations

import re
from datetime import date, datetime

from gl.fiscal_years.fy_calendar import fy_no_from_calendar_date

from .service_rules import is_audit_service, is_certification_service

_FY_TOKEN = re.compile(r"\bFY(\d{2})\b", re.I)
_YE_MARCH = re.compile(r"\b31[./-]0?3[./-](20\d{2})\b")


def normalize_service_fy(raw: str) -> str | None:
    """Return ``FY26``-style label or None if invalid."""
    text = (raw or "").strip().upper()
    if not text:
        return None
    code = text[:4] if len(text) >= 4 else text
    if len(code) == 4 and code.startswith("FY") and code[2:].isdigit():
        return code
    return None


def parse_udin_document_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    date_part = text.split("|", 1)[0].strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue
    return None


def _fy_from_remarks_for_audit(remarks: str) -> str | None:
    text = remarks or ""
    match = _FY_TOKEN.search(text)
    if match:
        return f"FY{match.group(1)}"
    match = _YE_MARCH.search(text)
    if match:
        end_year = int(match.group(1))
        return fy_no_from_calendar_date(date(end_year, 3, 31))
    return None


def derive_service_fy(
    *,
    service,
    date_of_signing_of_document: str = "",
    remarks: str = "",
    ay_fy: str = "",
) -> str | None:
    """
    Build Service FY for invoicing.

    Certification: fiscal year containing the document signing date.
    Audit: year to which the audit relates (YE 31.3.2026 → FY26), from
    existing AY/FY value or patterns in Remarks.
    """
    if is_certification_service(service):
        doc_date = parse_udin_document_date(date_of_signing_of_document)
        if doc_date is None:
            return None
        return fy_no_from_calendar_date(doc_date)

    if is_audit_service(service):
        normalized = normalize_service_fy(ay_fy)
        if normalized:
            return normalized
        return _fy_from_remarks_for_audit(remarks)

    if service is None:
        doc_date = parse_udin_document_date(date_of_signing_of_document)
        if doc_date is None:
            return None
        return fy_no_from_calendar_date(doc_date)

    return None
