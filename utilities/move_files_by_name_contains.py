"""Move direct child files when file name contains a phrase."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MoveByNameContainsReport:
    source_root: Path
    target_root: Path
    scanned_count: int = 0
    moved_count: int = 0
    matched_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def phrase_compact_date_month_error(phrase: str) -> str | None:
    """
    If ``phrase`` is only YYMM (4 digits) or only YYYYMM (6 digits with a
    plausible 4-digit year), require month 01–12. Otherwise return ``None``.
    """
    s = (phrase or "").strip()
    if re.fullmatch(r"\d{4}", s) is not None:
        mm = int(s[2:4])
        if not (1 <= mm <= 12):
            return "For YYMM, month (last two digits) must be between 01 and 12."
        return None
    if re.fullmatch(r"\d{6}", s) is not None:
        yyyy, mm = int(s[:4]), int(s[4:6])
        if 1800 <= yyyy <= 2199 and not (1 <= mm <= 12):
            return "For YYYYMM, month (last two digits) must be between 01 and 12."
        return None
    return None


def move_direct_files_name_contains(
    source_root: Path, target_root: Path, phrase: str
) -> MoveByNameContainsReport:
    report = MoveByNameContainsReport(source_root=source_root, target_root=target_root)
    needle = (phrase or "").strip()
    if not needle:
        raise ValueError("File name contains is required.")
    err = phrase_compact_date_month_error(needle)
    if err:
        raise ValueError(err)

    needle_l = needle.lower()
    for item in source_root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1
        if needle_l not in item.name.lower():
            continue
        report.matched_count += 1
        target = target_root / item.name
        if target.exists():
            report.skipped_paths.append(f"{item.name}: target already exists")
            continue
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{item.name}: {exc}")
            continue
        report.moved_count += 1
    return report
