"""
Audit / accounts document triage: find files by phrase (content + optional file name),
then move matches under a destination base into a category subfolder.

Uses the same phrase rules as ``file_content_search`` (phrase in order, first N words
for extracted text). Pair with ``audit_accounts_documents`` extensions where relevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utilities.audit_accounts_documents import AUDIT_ACCOUNTS_EXTENSIONS
from utilities.file_content_search import scan_folder_for_phrase


@dataclass(frozen=True)
class AuditTriageCategory:
    key: str
    label: str
    default_phrase: str
    folder_slug: str
    notes: str


# Ordered for UI; phrases are defaults — user may override per run.
AUDIT_TRIAGE_CATEGORIES: tuple[AuditTriageCategory, ...] = (
    AuditTriageCategory(
        key="audit_appointment",
        label="Audit appointment",
        default_phrase="letter of engagement",
        folder_slug="01_Audit_Appointment",
        notes="Engagement / appointment to audit.",
    ),
    AuditTriageCategory(
        key="acceptance",
        label="Acceptance",
        default_phrase="letter of acceptance",
        folder_slug="02_Acceptance",
        notes="Client acceptance of audit engagement or terms.",
    ),
    AuditTriageCategory(
        key="terms_conditions",
        label="Terms and conditions",
        default_phrase="terms and conditions",
        folder_slug="03_Terms_and_Conditions",
        notes="General terms, scope, fee schedules where bundled.",
    ),
    AuditTriageCategory(
        key="management_representation",
        label="Management representation",
        default_phrase="management representation",
        folder_slug="04_Management_Representation",
        notes="MR letter / representation from management.",
    ),
    AuditTriageCategory(
        key="final_accounts",
        label="Final accounts",
        default_phrase="financial statements",
        folder_slug="05_Final_Accounts",
        notes="Final financial statements / annual report pack.",
    ),
)


def category_by_key(key: str) -> AuditTriageCategory | None:
    k = (key or "").strip().lower()
    for c in AUDIT_TRIAGE_CATEGORIES:
        if c.key == k:
            return c
    return None


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def augment_matches_filename(
    root: Path, phrase: str, existing: list[str]
) -> list[str]:
    """Add files whose basename contains ``phrase`` (case-neutral), audit extensions only."""
    needle = phrase.strip().casefold()
    if not needle:
        return list(existing)
    root_r = root.expanduser().resolve()
    had = set(existing)
    out = list(existing)
    for p in root_r.rglob("*"):
        if not p.is_file():
            continue
        sp = str(p.resolve())
        if sp in had:
            continue
        if p.suffix.lower() not in AUDIT_ACCOUNTS_EXTENSIONS:
            continue
        if needle in p.name.casefold():
            out.append(sp)
            had.add(sp)
    return sorted(out)


def triage_scan_folder(
    root: Path,
    phrase: str,
    *,
    include_filename: bool,
    word_limit: int = 500,
):
    """Run content scan, optionally add filename hits for in-scope extensions."""
    report = scan_folder_for_phrase(root, phrase, word_limit=word_limit)
    if include_filename:
        report.matches = augment_matches_filename(root, phrase, report.matches)
    return report


@dataclass
class AuditTriageMoveReport:
    moved_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)


def _unique_destination(dest_dir: Path, filename: str) -> Path:
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for i in range(2, 10_000):
        alt = dest_dir / f"{stem}_{i}{suffix}"
        if not alt.exists():
            return alt
    raise OSError(f"No free destination name for {filename!r} under {dest_dir}")


def move_triage_matches(
    *,
    scan_root: Path,
    destination_base: Path,
    folder_slug: str,
    source_paths: list[str],
) -> AuditTriageMoveReport:
    """
    Move listed files into ``destination_base / folder_slug /``.

    Every path must be a file under ``scan_root`` (resolved) after resolution.
    """
    report = AuditTriageMoveReport()
    scan_r = scan_root.expanduser().resolve()
    dest_dir = (destination_base.expanduser().resolve() / folder_slug)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for raw in source_paths:
        s = (raw or "").strip()
        if not s:
            continue
        try:
            src = Path(s).expanduser().resolve()
        except OSError as exc:
            report.skipped_paths.append(f"{raw!r}: {exc}")
            continue
        if not src.is_file():
            report.skipped_paths.append(f"{src}: not a file")
            continue
        if not _is_under_root(src, scan_r):
            report.skipped_paths.append(f"{src}: outside scan folder")
            continue
        try:
            target = _unique_destination(dest_dir, src.name)
            src.rename(target)
            report.moved_count += 1
        except OSError as exc:
            report.skipped_paths.append(f"{src}: {exc}")
    return report


def triage_categories_as_dicts() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "key": c.key,
            "label": c.label,
            "default_phrase": c.default_phrase,
            "folder_slug": c.folder_slug,
            "notes": c.notes,
        }
        for c in AUDIT_TRIAGE_CATEGORIES
    )
