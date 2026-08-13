"""Detect duplicate files by signature and move extras to a target folder."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import shutil
from utilities.common import file_sha256

@dataclass
class DeleteDuplicateFilesReport:
    source_root: Path
    target_root: Path
    scanned_files: int = 0
    duplicate_groups: int = 0
    moved_files: int = 0
    moved_bytes: int = 0
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


ProgressCallback = Callable[[str, int, int | None, str], None]

def _is_relative_to(path: Path, maybe_parent: Path) -> bool:
    try:
        path.relative_to(maybe_parent)
        return True
    except ValueError:
        return False


def _next_available_destination(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    index = 1
    while True:
        option = parent / f"{stem} ({index}){suffix}"
        if not option.exists():
            return option
        index += 1


def move_duplicate_files_by_signature(
    source_root: Path,
    target_root: Path,
    progress_callback: ProgressCallback | None = None,
) -> DeleteDuplicateFilesReport:
    """
    Move duplicate files from source to target.

    Keeps one canonical file for each signature (the first file in sorted path order),
    and moves the rest into target_root preserving relative structure when possible.
    """
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    report = DeleteDuplicateFilesReport(source_root=source_root, target_root=target_root)
    def notify(phase: str, current: int, total: int | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(phase, current, total, message)

    if source_root == target_root:
        raise ValueError("Source and target folders cannot be the same.")
    if _is_relative_to(target_root, source_root) or _is_relative_to(source_root, target_root):
        raise ValueError("Source and target folders cannot be nested within each other.")

    by_size: dict[int, list[Path]] = {}
    notify("collecting", 0, None, "Scanning files...")
    for file_path in sorted(source_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.is_symlink():
            continue
        report.scanned_files += 1
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            report.skipped_paths.append(f"{file_path}: {exc}")
            continue
        by_size.setdefault(size, []).append(file_path)
        if report.scanned_files % 250 == 0:
            notify(
                "collecting",
                report.scanned_files,
                None,
                f"Scanned {report.scanned_files} files...",
            )

    notify("collecting", report.scanned_files, report.scanned_files, "Scan complete.")
    signature_map: dict[str, list[Path]] = {}
    hash_candidates = sum(
        len(paths) for paths in by_size.values() if len(paths) > 1
    )
    hashed_files = 0
    notify("hashing", 0, hash_candidates, "Hashing candidate files...")
    for same_size_paths in by_size.values():
        if len(same_size_paths) < 2:
            continue
        for file_path in same_size_paths:
            try:
                signature = file_sha256(file_path)
            except OSError as exc:
                report.skipped_paths.append(f"{file_path}: {exc}")
                continue
            signature_map.setdefault(signature, []).append(file_path)
            hashed_files += 1
            if hashed_files % 50 == 0 or hashed_files == hash_candidates:
                notify(
                    "hashing",
                    hashed_files,
                    hash_candidates,
                    f"Hashed {hashed_files}/{hash_candidates} candidate files...",
                )

    target_root.mkdir(parents=True, exist_ok=True)

    total_to_move = sum(max(0, len(paths) - 1) for paths in signature_map.values())
    moved_so_far = 0
    notify("moving", 0, total_to_move, "Moving duplicate files...")

    for duplicate_paths in signature_map.values():
        if len(duplicate_paths) < 2:
            continue
        sorted_paths = sorted(duplicate_paths, key=lambda path: str(path).lower())
        report.duplicate_groups += 1
        canonical = sorted_paths[0]
        for duplicate in sorted_paths[1:]:
            try:
                size = duplicate.stat().st_size
            except OSError as exc:
                report.skipped_paths.append(f"{duplicate}: {exc}")
                continue

            if _is_relative_to(duplicate, source_root):
                relative = duplicate.relative_to(source_root)
                destination = target_root / relative
            else:
                destination = target_root / duplicate.name

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = _next_available_destination(destination)

            try:
                shutil.move(str(duplicate), str(destination))
                report.moved_files += 1
                report.moved_bytes += size
                moved_so_far += 1
                if moved_so_far % 25 == 0 or moved_so_far == total_to_move:
                    notify(
                        "moving",
                        moved_so_far,
                        total_to_move,
                        f"Moved {moved_so_far}/{total_to_move} duplicate files...",
                    )
            except OSError as exc:
                report.skipped_paths.append(f"{duplicate} -> {destination}: {exc}")

        # Keep canonical untouched; this makes dedupe deterministic.
        _ = canonical

    notify("done", report.moved_files, report.moved_files, "Duplicate cleanup completed.")
    return report
