"""
Rules scaffold for **audit** and **accounts** working papers: renaming and filing.

Only these office formats are in scope for automated checks and future audit logs:
Word, PDF, PowerPoint, Excel. Other types (e.g. email, scans outside PDF) stay out of
this rule set until you extend it.

Downstream code (validators, rename helpers, audit log UI) should import from here
so naming and filing stay consistent.
"""

from __future__ import annotations

from typing import Any

# --- File classes (extensions lowercase, with leading dot) ---

AUDIT_ACCOUNTS_FILE_CLASSES: tuple[dict[str, Any], ...] = (
    {
        "key": "word",
        "label": "Word",
        "extensions": (".doc", ".docx", ".docm"),
        "role": "Programmes, planning memos, management letters, minutes, review notes.",
    },
    {
        "key": "pdf",
        "label": "PDF",
        "extensions": (".pdf",),
        "role": "Signed letters, filed financials, tax orders, client confirmations, immutable deliverables.",
    },
    {
        "key": "powerpoint",
        "label": "PowerPoint",
        "extensions": (".ppt", ".pptx", ".pptm"),
        "role": "Audit closing decks, internal training on engagement, presentation of findings.",
    },
    {
        "key": "excel",
        "label": "Excel",
        "extensions": (".xls", ".xlsx", ".xlsm", ".xlsb"),
        "role": "Lead schedules, TB tie-outs, analytical procedures, sampling, tax working papers.",
    },
)

# Flat set for path scanners / allow-lists
AUDIT_ACCOUNTS_EXTENSIONS: frozenset[str] = frozenset(
    ext for group in AUDIT_ACCOUNTS_FILE_CLASSES for ext in group["extensions"]
)


def extension_label(path_suffix: str) -> str | None:
    """Return Word / PDF / PowerPoint / Excel if suffix matches; else None."""
    s = path_suffix.lower().strip()
    if not s.startswith("."):
        s = "." + s
    for g in AUDIT_ACCOUNTS_FILE_CLASSES:
        if s in g["extensions"]:
            return g["label"]
    return None


# --- Naming rules (ordered tokens; implement enforcement later) ---

NAMING_RULES_AUDIT_ACCOUNTS: tuple[str, ...] = (
    "Use a fixed token order in the file name (same order as folders), e.g. "
    "FY → client code → engagement or entity → workpaper type → period or version → short descriptor.",
    "Separate tokens with a single agreed delimiter (hyphen or underscore); avoid spaces in machine paths.",
    "Prefer dates in ISO form YYYY-MM-DD inside names when the document is tied to a specific day.",
    "Use a version suffix only when needed (v2, final, signed); keep one convention for audit vs accounts.",
    "Do not embed volatile numbers (e.g. rupee totals) in the file name; keep amounts inside the file.",
    "Keep file names ASCII-safe where possible; replace slashes and reserved Windows characters.",
)

# --- Filing rules (folder hierarchy aligned with names) ---

FILING_RULES_AUDIT_ACCOUNTS: tuple[str, ...] = (
    "Root by fiscal year (or statutory year for tax), then client or entity, then engagement or workstream.",
    "Under engagement, split Audit vs Accounts / Tax at a top level so search and permissions can differ.",
    "Keep Excel lead sheets and PDF finals in predictable siblings (e.g. …/working/ vs …/deliverables/).",
    "Do not mix personal or unrelated documents inside audit or accounts trees; use a general inbox instead.",
    "After rename or move, relative path plus basename should still reflect the same token set as the file name.",
)

OUT_OF_SCOPE_NOTE: str = (
    "E-mail (.msg / .eml), scans not stored as PDF, databases, and media are out of scope for this rule pack "
    "unless you extend AUDIT_ACCOUNTS_FILE_CLASSES."
)
