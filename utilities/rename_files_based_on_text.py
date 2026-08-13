"""Rename direct child files using identifier-based text trimming."""

from __future__ import annotations

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


def rename_direct_files_by_text(
    root: Path,
    *,
    identifier: str,
    criteria: str,
) -> RenameByTextReport:
    report = RenameByTextReport(root=root)
    ident = (identifier or "").strip()
    if not ident:
        raise ValueError("File name text Identifier is required.")
    if criteria not in {"remove_left", "remove_right"}:
        raise ValueError("Rename criteria is invalid.")

    ident_len = len(ident)
    ident_l = ident.lower()

    for item in root.iterdir():
        if not item.is_file():
            continue
        report.scanned_count += 1

        original_name = item.name
        stem = item.stem
        suffix = item.suffix
        pos = stem.lower().find(ident_l)
        if pos < 0:
            report.skipped_paths.append(f"{original_name}: identifier not found")
            continue

        if criteria == "remove_left":
            new_stem = stem[pos:]
        else:
            new_stem = stem[: pos + ident_len]

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
