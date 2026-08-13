"""Derive UDIN service_remarks from Remarks (ICAI) + Client (for Certification invoicing)."""

from __future__ import annotations

import re

from sales.clients.models import Client

from .models import Udin
from .service_rules import is_audit_service, is_certification_service

CERTIFICATION_FEE_PREFIX = "Fee for issuing certificate for "


def service_remarks_is_blank(value: str | None) -> bool:
    return not (value or "").strip()


def _remarks_word_tokens(remarks: str) -> list[str]:
    return re.findall(r"\b[A-Za-z0-9]+\b", (remarks or "").upper())


def find_client_by_code_in_remarks(remarks: str) -> Client | None:
    """
    Match Client.client_code anywhere in Remarks.

    Whole-word and bounded substring matches (full text scan), plus prefix match
    when a remarks token is a shorter form of the 4-char code (e.g. RSL → RSL1).
    """
    text = (remarks or "").strip()
    if not text:
        return None
    text_upper = text.upper()
    tokens = _remarks_word_tokens(text)
    token_set = set(tokens)

    best: Client | None = None
    best_score = -1

    for row in Client.objects.exclude(client_code="").only(
        "id", "client_code", "client_name", "client_short_name"
    ):
        code = (row.client_code or "").strip().upper()
        if not code:
            continue

        score = -1
        if code in token_set:
            score = 1000 + len(code)
        else:
            for tok in tokens:
                if len(tok) < 3:
                    continue
                if code.startswith(tok):
                    score = max(score, 500 + len(tok))
                elif tok.startswith(code) and len(code) >= 3:
                    score = max(score, 400 + len(code))

        if score < 0 and len(code) >= 3:
            if re.search(
                rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])",
                text_upper,
            ):
                score = 300 + len(code)

        if score < 0:
            continue
        if score > best_score or (
            score == best_score
            and best is not None
            and len(code) > len((best.client_code or "").strip())
        ):
            best_score = score
            best = row

    return best


def resolve_client_for_remarks(*, remarks: str, client) -> Client | None:
    if client is not None:
        return client
    return find_client_by_code_in_remarks(remarks)


def bulk_fill_client_from_remarks() -> tuple[int, int]:
    """Set Client on all UDINs whose Remarks contain a matching client code."""
    updated = 0
    skipped = 0
    for udin in Udin.objects.select_related("client").iterator():
        matched = find_client_by_code_in_remarks(udin.remarks or "")
        if matched is None:
            skipped += 1
            continue
        if udin.client_id == matched.pk:
            skipped += 1
            continue
        udin.client = matched
        udin.save(update_fields=["client", "updated_on"])
        updated += 1
    return updated, skipped


def strip_remarks_client_code(*, remarks: str, client) -> str | None:
    """
    Step 2: drop leading client code from ICAI Remarks (must match Client.client_code).
    """
    text = (remarks or "").strip()
    if not text or client is None:
        return None
    code = (getattr(client, "client_code", None) or "").strip()
    if not code:
        return None
    parts = text.split(None, 1)
    if len(parts) < 2 or parts[0].upper() != code.upper():
        return None
    return parts[1].strip()


def build_certification_service_remarks(*, stripped_remarks: str) -> str:
    """Step 3: full invoice line for the Service remarks field."""
    body = (stripped_remarks or "").strip()
    if not body:
        return ""
    line = f"{CERTIFICATION_FEE_PREFIX}{body}"
    return line if line.endswith(".") else f"{line}."


def derive_service_remarks(*, remarks: str, client, service) -> str | None:
    """
    Certification billing prep (updates **Service remarks**, reads **Remarks**):

    1. Read Remarks (ICAI text, e.g. ``SVSM Form 146 FILOPA 20260502``)
    2. Strip client code (``SVSM``) using Client master
    3. ``Fee for issuing certificate for `` + stripped text (trimmed)
    """
    if service is not None and is_audit_service(service):
        return None
    if service is not None and not is_certification_service(service):
        return None

    text = (remarks or "").strip()
    if not text:
        return None

    client = resolve_client_for_remarks(remarks=text, client=client)
    stripped = strip_remarks_client_code(remarks=text, client=client)
    if not stripped:
        return None
    return build_certification_service_remarks(stripped_remarks=stripped)


def explain_service_remarks_failure(*, remarks: str, client, service) -> str:
    if service is not None and is_audit_service(service):
        return (
            f"Service is “{service.service_desc}”. Update service remarks uses Certification "
            "rules only — set Service to Certification or leave it blank."
        )
    if service is not None and not is_certification_service(service):
        return (
            f"Service is “{service.service_desc}”. Update service remarks uses Certification "
            "rules only."
        )
    if not (remarks or "").strip():
        return "Remarks (ICAI) is empty — nothing to read."
    client = resolve_client_for_remarks(remarks=remarks, client=client)
    code = (getattr(client, "client_code", None) or "").strip() if client else ""
    if not client or not code:
        return (
            "Set Client (or start Remarks with a client code that exists in Clients master, "
            "e.g. SVSM Form 146 …)."
        )
    parts = (remarks or "").strip().split(None, 1)
    if len(parts) < 2 or parts[0].upper() != code.upper():
        return (
            f"Remarks must start with client code {code} followed by certificate text "
            f"(e.g. {code} Form 146 FILOPA 20260502)."
        )
    return "Could not build service remarks from Remarks."
