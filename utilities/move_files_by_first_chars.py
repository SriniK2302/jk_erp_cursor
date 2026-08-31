"""Move direct child files into folders named after their first N characters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MoveByFirstCharsReport:
    root: Path
    scanned_count: int = 0
    moved_count: int = 0
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


def move_direct_files_by_first_chars(root: Path, *, char_count: int) -> MoveByFirstCharsReport:
    """
    Move only files directly inside root (subfolders are not scanned or
    processed) into folders named after the first ``char_count`` characters
    of each file's stem (name without extension). If the stem is shorter
    than ``char_count``, the whole stem is used. Grouping is
    case-insensitive; the folder name uses the case of whichever file is
    processed first for that group. If a file with the same name already
    exists in the target folder, the moved file is renamed (e.g. " v2")
    rather than overwriting or being skipped.
    """
    report = MoveByFirstCharsReport(root=root)
    if char_count < 1:
        raise ValueError("Number of characters must be at least 1.")

    folder_names: dict[str, str] = {}  # lowercase key -> actual folder name used

    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1

        name = item.name
        stem = item.stem
        suffix = item.suffix
        prefix = stem[:char_count] if stem else name[:char_count]
        if not prefix:
            report.skipped_paths.append(f"{name}: no characters available to group by")
            continue

        key = prefix.lower()
        folder_name = folder_names.setdefault(key, prefix)
        target_folder = root / folder_name

        try:
            target_folder.mkdir(parents=False, exist_ok=True)
        except OSError as exc:
            report.skipped_paths.append(f"{name}: cannot create {folder_name} ({exc})")
            continue

        final_name = _next_available_name(target_folder, stem, suffix)
        target = target_folder / final_name

        try:
            item.rename(target)
        except OSError as exc:
            report.skipped_paths.append(f"{name}: {exc}")
            continue
        report.moved_count += 1

    return report
