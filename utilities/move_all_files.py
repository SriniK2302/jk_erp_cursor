"""Move all files from a source folder (including all subfolders) into a
single target folder as flat files (no subfolder structure), then delete
any empty folders left behind under the source."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import shutil


@dataclass
class MoveAllFilesReport:
    source_root: Path
    target_root: Path
    scanned_files: int = 0
    moved_files: int = 0
    moved_bytes: int = 0
    renamed_count: int = 0
    deleted_folders: int = 0
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
    """Return candidate, or candidate renamed as 'name (1).ext', 'name (2).ext', ...
    if a file with that name already exists at the destination (Windows style)."""
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


def move_all_files_flat(
    source_root: Path,
    target_root: Path,
    progress_callback: ProgressCallback | None = None,
) -> MoveAllFilesReport:
    """
    Move every file under source_root (including all subfolders) directly
    into target_root as a flat file list (no subfolders created in target).

    If a file of the same name already exists at the destination, the moved
    file is renamed with a Windows-style " (1)", " (2)", ... suffix.

    After all files are moved, every empty folder remaining under
    source_root (including source_root itself, if empty) is deleted.
    """
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    report = MoveAllFilesReport(source_root=source_root, target_root=target_root)

    def notify(phase: str, current: int, total: int | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(phase, current, total, message)

    if source_root == target_root:
        raise ValueError("Source and target folders cannot be the same.")
    if _is_relative_to(target_root, source_root) or _is_relative_to(source_root, target_root):
        raise ValueError("Source and target folders cannot be nested within each other.")

    notify("collecting", 0, None, "Scanning files...")
    all_files: list[Path] = []
    for file_path in sorted(source_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.is_symlink():
            continue
        all_files.append(file_path)
        if len(all_files) % 250 == 0:
            notify("collecting", len(all_files), None, f"Scanned {len(all_files)} files...")

    report.scanned_files = len(all_files)
    notify("collecting", report.scanned_files, report.scanned_files, "Scan complete.")

    target_root.mkdir(parents=True, exist_ok=True)

    total_to_move = len(all_files)
    notify("moving", 0, total_to_move, "Moving files...")

    for file_path in all_files:
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            report.skipped_paths.append(f"{file_path}: {exc}")
            continue

        destination = target_root / file_path.name
        final_destination = _next_available_destination(destination)
        if final_destination != destination:
            report.renamed_count += 1

        try:
            shutil.move(str(file_path), str(final_destination))
            report.moved_files += 1
            report.moved_bytes += size
            if report.moved_files % 25 == 0 or report.moved_files == total_to_move:
                notify(
                    "moving",
                    report.moved_files,
                    total_to_move,
                    f"Moved {report.moved_files}/{total_to_move} files...",
                )
        except OSError as exc:
            report.skipped_paths.append(f"{file_path} -> {final_destination}: {exc}")

    notify("cleanup", 0, None, "Removing empty folders...")
    for directory in sorted(
        source_root.rglob("*"), key=lambda path: len(path.parts), reverse=True
    ):
        if not directory.is_dir():
            continue
        try:
            next(directory.iterdir())
        except StopIteration:
            try:
                directory.rmdir()
                report.deleted_folders += 1
            except OSError as exc:
                report.skipped_paths.append(f"{directory}: {exc}")
        except OSError as exc:
            report.skipped_paths.append(f"{directory}: {exc}")

    try:
        next(source_root.iterdir())
    except StopIteration:
        try:
            source_root.rmdir()
            report.deleted_folders += 1
        except OSError as exc:
            report.skipped_paths.append(f"{source_root}: {exc}")
    except OSError:
        pass

    notify("done", report.moved_files, report.moved_files, "Move completed.")
    return report
