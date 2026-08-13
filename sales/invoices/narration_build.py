"""Build suggested invoice narration from UDIN + JSON templates (see data/narration_templates.json)."""

from __future__ import annotations

import json
from pathlib import Path

from sales.udins.service_remarks_build import (
    CERTIFICATION_FEE_PREFIX,
    build_certification_service_remarks,
)
from sales.udins.service_rules import is_certification_service

_DATA_FILE = Path(__file__).resolve().parent / "data" / "narration_templates.json"
_templates_cache: dict | None = None


def reload_narration_templates() -> None:
    """Clear cached JSON (e.g. after editing narration_templates.json in tests)."""
    global _templates_cache
    _templates_cache = None


def _load_templates() -> dict:
    global _templates_cache
    if _templates_cache is not None:
        return _templates_cache
    if not _DATA_FILE.is_file():
        _templates_cache = {
            "default_template": "",
            "by_service_code": {},
            "by_service_desc": {},
        }
        return _templates_cache
    with open(_DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    _templates_cache = {
        "default_template": (raw.get("default_template") or "").strip(),
        "by_service_code": raw.get("by_service_code") or {},
        "by_service_desc": raw.get("by_service_desc") or {},
    }
    return _templates_cache


def narration_suggestion_for_udin(udin) -> str:
    """
    Return text for the narration field from the selected UDIN's service + placeholders.

    Template lookup: service_code, exact service_desc, case-insensitive service_desc,
    then default_template.

    Placeholders: {service_remarks}, {fy_no} / {FYno} (from UDIN.ay_fy).
    """
    data = _load_templates()
    service = udin.service
    if not service:
        return ""

    desc = (service.service_desc or "").strip()
    code = (service.service_code or "").strip()
    tpl = data["by_service_code"].get(code)
    if tpl is None:
        tpl = data["by_service_desc"].get(desc)
    if tpl is None and desc:
        desc_lower = desc.lower()
        for key, val in data["by_service_desc"].items():
            if str(key).startswith("_"):
                continue
            if str(key).lower() == desc_lower:
                tpl = val
                break
    if tpl is None and desc:
        desc_lower = desc.lower()
        best = None  # (len_key, key, val) — pick longest matching key
        for key, val in data["by_service_desc"].items():
            if str(key).startswith("_"):
                continue
            k = str(key).strip()
            if not k:
                continue
            kl = k.lower()
            if desc_lower == kl or desc_lower.startswith(kl + " ") or desc_lower.startswith(kl + "-"):
                cand = (len(kl), k, val)
                if best is None or cand[0] > best[0]:
                    best = cand
        if best is not None:
            tpl = best[2]
    if tpl is None:
        tpl = data["default_template"] or ""
    if not tpl:
        remarks = (getattr(udin, "service_remarks", None) or "").strip()
        if remarks:
            return f"Fee for professional services: {remarks}."
        if desc:
            return f"Fee for professional services: {desc}."
        return ""

    return _apply_placeholders(tpl, udin)


def _apply_placeholders(tpl: str, udin) -> str:
    remarks = (getattr(udin, "service_remarks", None) or "").strip()
    service = getattr(udin, "service", None)
    if service and is_certification_service(service) and remarks:
        if not remarks.lower().startswith(CERTIFICATION_FEE_PREFIX.lower()):
            remarks = build_certification_service_remarks(stripped_remarks=remarks)
    fy = (getattr(udin, "ay_fy", None) or "").strip()
    out = tpl
    out = out.replace("{service_remarks}", remarks)
    out = out.replace("{FYno}", fy).replace("{fy_no}", fy)
    return " ".join(out.split()).strip()


def header_narration_from_udin_rows(map_rows) -> str:
    """
    Invoice-level narration from validated map rows ``(udin, service_desc, line_amount)``.

    Each UDIN contributes at most one template-based suggestion; duplicates are skipped;
    multiple distinct suggestions are joined with ``; `` (order follows fee lines).
    """
    parts: list[str] = []
    seen: set[str] = set()
    for row in map_rows:
        udin = row[0]
        s = narration_suggestion_for_udin(udin).strip()
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
    return "; ".join(parts) if parts else ""


def invoice_header_narration_for_display(invoice) -> str:
    """
    Text for invoice header / GSTR1: saved ``invoice.narration`` if set; otherwise the same
    synthesis as ``header_narration_from_udin_rows`` from persisted maps.
    """
    raw = (invoice.narration or "").strip()
    if raw:
        return " ".join(raw.split())
    maps = invoice.inv_udin_maps.order_by("line_no").select_related("udin", "udin__service")
    synth_rows = []
    for m in maps:
        if not m.udin_id:
            continue
        synth_rows.append((m.udin, (m.service_desc or "").strip(), m.line_amount))
    return header_narration_from_udin_rows(synth_rows) if synth_rows else ""
