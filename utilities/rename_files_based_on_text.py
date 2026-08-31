"""Rename direct child files using identifier-based text trimming."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenameByTextReport:
    root: Path
    scanned_count: int = 0
    renamed_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _next_available_name(folder: Path, stem: str, suffix: str) -> str:
    base = f"{stem}{suffix}"
    if not (folder / base).exists():
        return base
    n = 2
    while True:
        candidate = f"{stem} v{n}{suffix}"
        if not (folder / candidate).exists():
            return candidate
        n += 1


def _collapse_spaces(text: str) -> str:
    """Collapse runs of 2+ spaces into a single space, and trim ends."""
    return re.sub(r" {2,}", " ", text).strip()


def _expand_identifier_range(identifier: str) -> list[str]:
    """
    Expand an identifier spec into a list of candidate match strings.

    Formats supported:
      - "TEXT"                -> single exact identifier: ["TEXT"]
      - "FROM:TO"              -> range, default trailing digit width = 2
      - "FROM:TO;WIDTH"        -> range, trailing digit width = WIDTH

    The trailing WIDTH digits of FROM and TO are treated as the varying
    numeric part; everything before them must match between FROM and TO
    (the fixed prefix) or the spec is treated as a plain single identifier.
    """
    raw = (identifier or "").strip()
    if ":" not in raw:
        return [raw] if raw else []

    range_part, _, width_part = raw.partition(";")
    from_str, _, to_str = range_part.partition(":")
    from_str = from_str.strip()
    to_str = to_str.strip()

    width = 2
    if width_part.strip():
        try:
            width = int(width_part.strip())
        except ValueError:
            width = 2
    if width < 1:
        width = 2

    if len(from_str) < width or len(to_str) < width:
        return [raw]

    from_prefix, from_digits = from_str[:-width], from_str[-width:]
    to_prefix, to_digits = to_str[:-width], to_str[-width:]

    if from_prefix != to_prefix or not from_digits.isdigit() or not to_digits.isdigit():
        return [raw]

    start = int(from_digits)
    end = int(to_digits)
    if start > end:
        start, end = end, start

    return [f"{from_prefix}{n:0{width}d}" for n in range(start, end + 1)]


def _find_exact_match(stem_l: str, cand_l: str) -> int:
    """
    Find ``cand_l`` inside ``stem_l`` as an exact token: the character
    immediately before and after the match (if any) must not be a digit.
    This stops "04" from matching inside "042" or "1204".
    Returns the match start index, or -1 if no exact match is found.
    """
    if not cand_l:
        return -1
    start = 0
    while True:
        pos = stem_l.find(cand_l, start)
        if pos < 0:
            return -1
        end = pos + len(cand_l)
        before_ok = pos == 0 or not stem_l[pos - 1].isdigit()
        after_ok = end == len(stem_l) or not stem_l[end].isdigit()
        if before_ok and after_ok:
            return pos
        start = pos + 1


def rename_direct_files_by_text(
    root: Path,
    *,
    identifier: str,
    prefix: str = "",
) -> RenameByTextReport:
    report = RenameByTextReport(root=root)
    candidates = _expand_identifier_range(identifier)
    if not candidates:
        raise ValueError("File name text Identifier is required.")

    candidates_l = [c.lower() for c in candidates]
    prefix = prefix or ""

    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1

        original_name = item.name
        stem = item.stem
        suffix = item.suffix
        stem_l = stem.lower()

        pos = -1
        for cand_l in candidates_l:
            found = _find_exact_match(stem_l, cand_l)
            if found >= 0:
                pos = found
                break

        if pos < 0:
            report.skipped_paths.append(f"{original_name}: identifier not found")
            continue

        if prefix and (stem == prefix or stem.startswith(prefix + " ")):
            report.skipped_paths.append(f"{original_name}: Compliant")
            continue
        
        new_stem = stem[pos:]

        if prefix:
            new_stem = f"{prefix} {new_stem}"
        new_stem = _collapse_spaces(new_stem)

        if not new_stem:
            report.skipped_paths.append(f"{original_name}: resulting file name is empty")
            continue

        final_name = _next_available_name(root, new_stem, suffix)
        if final_name == original_name:
            continue

        target = item.with_name(final_name)
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{original_name}: {exc}")
            continue
        report.renamed_count += 1

    return report
