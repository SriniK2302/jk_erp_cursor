"""Move direct child files into FY folders from a leading ``YYYY MM DD`` or ``YYYY MM`` prefix."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import re

from gl.fiscal_years.fy_calendar import fy_no_from_calendar_date


_DATE_PREFIX_YMD = re.compile(r"^(\d{4}) (\d{2}) (\d{2})")
_DATE_PREFIX_YM = re.compile(r"^(\d{4}) (\d{2})$")


@dataclass
class MoveToFyReport:
    root: Path
    scanned_count: int = 0
    moved_count: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _parse_date_from_file_prefix(file_name: str) -> date | None:
    """
    Parse **only the left-hand prefix** of ``file_name``: ``YYYY MM DD`` (first
    10 chars) or ``YYYY MM`` (first 7 chars; day defaults to 1). Prefer the
    longer match when both are possible. (FY folder move does not scan the
    middle of the name.)
    """
    if len(file_name) >= 10:
        m = _DATE_PREFIX_YMD.match(file_name[:10])
        if m:
            yyyy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mm <= 12:
                try:
                    return date(yyyy, mm, dd)
                except ValueError:
                    pass
    if len(file_name) >= 7:
        m = _DATE_PREFIX_YM.match(file_name[:7])
        if m:
            yyyy, mm = int(m.group(1)), int(m.group(2))
            if 1 <= mm <= 12:
                try:
                    return date(yyyy, mm, 1)
                except ValueError:
                    pass
    return None


def move_direct_files_to_fy_folders(root: Path) -> MoveToFyReport:
    """Move only files directly inside root into computed FY folders (FYxx)."""
    report = MoveToFyReport(root=root)
    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1
        dt = _parse_date_from_file_prefix(item.name)
        if dt is None:
            report.skipped_paths.append(
                f"{item.name}: name does not start with valid 'YYYY MM DD' or 'YYYY MM'"
            )
            continue

        fy_folder = root / fy_no_from_calendar_date(dt)
        try:
            fy_folder.mkdir(parents=False, exist_ok=True)
        except OSError as exc:
            report.skipped_paths.append(f"{item.name}: cannot create {fy_folder.name} ({exc})")
            continue

        target = fy_folder / item.name
        if target.exists():
            report.skipped_paths.append(
                f"{item.name}: target already exists in {fy_folder.name}"
            )
            continue
        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{item.name}: {exc}")
            continue
        report.moved_count += 1

    return report
