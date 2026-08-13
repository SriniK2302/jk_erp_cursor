"""Fill .docx Word templates for engagement documentation using ``{{TOKEN}}`` placeholders."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, BinaryIO

from django.conf import settings
from django.utils import timezone
from xml.sax.saxutils import escape

if TYPE_CHECKING:
    from engagements.models import EngagementDocumentationMap

# Placeholders must match tokens used in templates / word_merge_tokens.json
_TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def format_letter_date_display(d: date) -> str:
    """Day.month.year without zero-padding (e.g. ``1.7.2025``)."""
    return f"{d.day}.{d.month}.{d.year}"


_ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def format_date_english_long(d: date) -> str:
    """e.g. ``31 March 2026`` (for audit period / MR wording)."""
    return f"{d.day} {_ENGLISH_MONTHS[d.month - 1]} {d.year}"


def format_day_month_english(d: date) -> str:
    """e.g. ``31 March`` (no year)."""
    return f"{d.day} {_ENGLISH_MONTHS[d.month - 1]}"


def _trailing_locality_before_pincode(address_line: str) -> str:
    """Best-effort city/locality before a 6-digit Indian pincode on the last comma segment."""
    addr = (address_line or "").strip()
    if not addr:
        return ""
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    if not parts:
        return ""
    tail = re.sub(r"\s*\d{6}\s*$", "", parts[-1]).strip()
    if not tail:
        return ""
    return tail.split()[-1]


def _client_place_for_documents(client) -> str:
    """Short place name under client letterhead (e.g. city)."""
    area = (getattr(client, "area", None) or "").strip()
    if area:
        return area
    csp = (getattr(client, "city_state_pincode", None) or "").strip()
    if not csp:
        return ""
    if "," in csp:
        return csp.split(",")[0].strip()
    return csp


def _letterhead_str(letterhead: dict, key: str) -> str:
    v = letterhead.get(key) if isinstance(letterhead, dict) else None
    if v is None:
        return ""
    return str(v).strip()


_WIN_FILE_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_attachment_text(s: str) -> str:
    """Strip characters invalid in Windows filenames; collapse whitespace."""
    s = _WIN_FILE_FORBIDDEN.sub("", (s or "").strip())
    return " ".join(s.split())


def _standard_document_tail_for_filename(standard_document: str, *, max_chars: int = 80) -> str:
    s = _safe_attachment_text(standard_document)
    if len(s) <= max_chars:
        return s
    trimmed = s[:max_chars].rsplit(" ", 1)[0]
    return trimmed if trimmed else s[:max_chars]


# Longest first so the most specific phrase is removed when several could match.
_STATUTORY_AUDIT_TITLE_SUFFIXES: tuple[str, ...] = (
    " for statutory audit of corporate",
    " for statutory audit of llp",
    " for statutory audit of company",
    " for statutory audit of partnership firm",
    " for statutory audit of partnership",
    " for statutory audit",
)


def _strip_redundant_statutory_audit_title_tail(text: str) -> str:
    """Drop trailing ``for statutory audit …`` when service code already encodes the service."""
    t = (text or "").strip()
    if not t:
        return ""
    changed = True
    while changed:
        changed = False
        low = t.lower()
        for suf in _STATUTORY_AUDIT_TITLE_SUFFIXES:
            if low.endswith(suf):
                t = t[: -len(suf)].rstrip(" -–—")
                changed = True
                break
    return t


def _title_for_filled_docx_filename(standard_document: str) -> str:
    """Short, path-friendly tail after removing redundant audit boilerplate."""
    s = _strip_redundant_statutory_audit_title_tail(_safe_attachment_text(standard_document))
    return _standard_document_tail_for_filename(s, max_chars=40)


def filled_engagement_documentation_docx_filename(
    *,
    documentation_date: date,
    fy_no: str,
    client_code: str,
    service_code: str,
    standard_document: str,
    filled_download_label: str = "",
) -> str:
    """Suggested download name for a filled template: ``YYYY MM DD FY client_code service_code title.docx``.

    When ``filled_download_label`` is set on the setup row (e.g. ``MR 01``), it is used as the
    title segment. Otherwise the title is shortened from the standard document (redundant
    ``for statutory audit …`` dropped, then a 40-char word-safe cap).
    """
    date_part = documentation_date.strftime("%Y %m %d")
    fy_s = _safe_attachment_text(fy_no)
    cc_s = _safe_attachment_text(client_code)
    sc_s = _safe_attachment_text(service_code)
    label = _safe_attachment_text(filled_download_label)
    title = label if label else _title_for_filled_docx_filename(standard_document)
    fixed = " ".join(p for p in (date_part, fy_s, cc_s, sc_s) if p).strip()
    name = f"{fixed} {title}".strip(" .") if title else fixed
    if not name:
        name = "document"
    # Keep stems short for nested folders / backup tools (Windows path limits, etc.).
    max_stem = 110
    if len(name) > max_stem:
        room = max_stem - len(fixed) - (1 if fixed and title else 0)
        if room < 8:
            name = fixed[:max_stem].rstrip(" .")
        else:
            short_title = _standard_document_tail_for_filename(title, max_chars=max(room, 8))
            name = f"{fixed} {short_title}".strip(" .")
            if len(name) > max_stem:
                name = name[:max_stem].rstrip(" .")
    if not name.lower().endswith(".docx"):
        name = f"{name}.docx"
    return name


def merge_context_for_engagement(
    engagement,
    *,
    documentation_map: EngagementDocumentationMap | None = None,
) -> dict[str, str]:
    """Build ``{{TOKEN}}`` → replacement text from engagement + client + settings.

    ``{{LETTER_DATE}}`` uses the documentation map's list date (``documentation_date``)
    when ``documentation_map`` is passed (Fill Word from the engagement list); otherwise
    today's local date.
    """
    client = engagement.client
    fy = engagement.fiscal_year
    svc = engagement.service
    letterhead = getattr(settings, "INVOICE_LETTERHEAD", None) or {}

    line1 = (client.address_1 or "").strip()
    line2 = (client.address_2 or client.area or "").strip()
    line3 = (client.city_state_pincode or "").strip()
    if not line2 and (getattr(client, "state", None) or getattr(client, "pincode", None)):
        line2 = " ".join(
            p
            for p in [
                (client.state or "").strip(),
                (client.pincode or "").strip(),
            ]
            if p
        ).strip()

    fee_amt: Decimal | None = getattr(engagement, "fee_amount", None)
    fee_fig = ""
    if fee_amt is not None:
        fee_fig = f"{fee_amt:,.2f}"

    frf_parts = []
    if letterhead.get("firm_pan"):
        frf_parts.append(f"PAN {letterhead['firm_pan']}")
    if letterhead.get("firm_gstn"):
        frf_parts.append(f"GST {letterhead['firm_gstn']}")
    frf = " · ".join(frf_parts)

    if documentation_map is not None:
        letter_d = documentation_map.documentation_date
    else:
        letter_d = timezone.localdate()
    letter_date_dm = format_letter_date_display(letter_d)
    fy_end = getattr(fy, "end_date", None)
    fy_end_year = str(fy_end.year) if fy_end else ""
    fy_end_date_phrase = format_date_english_long(fy_end) if fy_end else ""
    fy_end_day_month = format_day_month_english(fy_end) if fy_end else ""
    year_ended_phrase = (
        f"year ended {fy_end_date_phrase}" if fy_end_date_phrase else ""
    )
    firm_name_disp = _letterhead_str(letterhead, "firm_name")
    if firm_name_disp.isupper():
        firm_name_disp = firm_name_disp.title()
    auditor_city = _letterhead_str(letterhead, "firm_office_city") or _trailing_locality_before_pincode(
        _letterhead_str(letterhead, "address_line_1")
    )
    signatory_name = (getattr(client, "contact_person", None) or "").strip()
    signatory_desig = _letterhead_str(
        letterhead, "management_rep_signatory_designation"
    )
    return {
        "{{LETTER_DATE}}": letter_date_dm,
        "{{MR_DATE}}": letter_date_dm,
        "{{CLIENT_NAME}}": (client.client_name or "").strip(),
        "{{CLIENT_PLACE}}": _client_place_for_documents(client),
        "{{CLIENT_ADDRESS_LINE_1}}": line1,
        "{{CLIENT_ADDRESS_LINE_2}}": line2,
        "{{CLIENT_ADDRESS_LINE_3}}": line3,
        "{{FY_YEAR}}": (fy.fy_no or "").strip(),
        "{{FY_END_YEAR}}": fy_end_year,
        "{{FY_END_DATE_PHRASE}}": fy_end_date_phrase,
        "{{FY_END_DAY_MONTH}}": fy_end_day_month,
        "{{YEAR_ENDED_PHRASE}}": year_ended_phrase,
        "{{FRF}}": frf,
        "{{AUDIT_FEE_AMOUNT}}": fee_fig,
        "{{AUDIT_FEE_WORDS}}": "",
        "{{PARTNER_NAME}}": (letterhead.get("authorised_signatory_name") or "").strip(),
        "{{MEMBERSHIP_NO}}": "",
        "{{SERVICE_DESC}}": (svc.service_desc or "").strip(),
        "{{AUDITOR_TO_LINE_1}}": firm_name_disp,
        "{{AUDITOR_TO_LINE_2}}": _letterhead_str(letterhead, "firm_subtitle"),
        "{{AUDITOR_TO_LINE_3}}": auditor_city,
        "{{SIGNATORY_NAME}}": signatory_name,
        "{{SIGNATORY_DESIGNATION}}": signatory_desig,
    }


def fill_docx_template(template_stream: BinaryIO, replacements: dict[str, str]) -> bytes:
    """
    Copy a .docx package, replacing known ``{{TOKEN}}`` substrings in ``word/**/*.xml``.
    Contiguous tokens only (same as Word often stores for plain typed placeholders).
    """
    src = template_stream.read()
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src), "r") as zin:
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if (
                    info.filename.startswith("word/")
                    and info.filename.endswith(".xml")
                    and not info.filename.endswith(".rels")
                ):
                    text = data.decode("utf-8")
                    for token, raw_val in replacements.items():
                        if token in text:
                            text = text.replace(token, escape(raw_val or ""))
                    data = text.encode("utf-8")
                zout.writestr(info, data)
    return out_buf.getvalue()


def list_unresolved_tokens_in_document_xml(docx_bytes: bytes) -> list[str]:
    """Return distinct ``TOKEN`` names still present as ``{{TOKEN}}`` in ``word/document.xml``."""
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
            raw = zf.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile):
        return []
    text = raw.decode("utf-8", errors="replace")
    return sorted(set(_TOKEN_RE.findall(text)))
