"""Delete empty folders from a selected root directory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
#from tkinter import Tk, TclError, filedialog


@dataclass
class DeleteEmptyFoldersReport:
    root: Path
    scanned_count: int = 0
    deleted_paths: list[Path] = field(default_factory=list)
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_paths)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def choose_root_folder() -> Path | None:
    """
    Open a native folder picker and return the selected path.

    Returns None when selection is cancelled.
    Raises RuntimeError if the GUI cannot be launched.
    """
    try:
        from tkinter import Tk, TclError, filedialog
    except ImportError as exc:
        raise RuntimeError(
            "Folder picker requires a desktop environment with tkinter; "
            "not available on this server."
        ) from exc

    try:
        picker_root = Tk()
        picker_root.withdraw()
        picker_root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Select root folder to delete empty subfolders",
            mustexist=True,
        )
        picker_root.destroy()
    except TclError as exc:
        raise RuntimeError("Unable to launch folder picker.") from exc

    if not selected:
        return None
    return Path(selected)


def delete_empty_folders_under(root: Path) -> DeleteEmptyFoldersReport:
    """Delete all empty folders under root (including root if empty)."""
    report = DeleteEmptyFoldersReport(root=root)

    for directory in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if not directory.is_dir():
            continue
        report.scanned_count += 1
        try:
            next(directory.iterdir())
        except StopIteration:
            try:
                directory.rmdir()
                report.deleted_paths.append(directory)
            except OSError as exc:
                report.skipped_paths.append(f"{directory}: {exc}")
        except OSError as exc:
            report.skipped_paths.append(f"{directory}: {exc}")

    # Check root at the end so already-removed children are considered.
    report.scanned_count += 1
    try:
        next(root.iterdir())
    except StopIteration:
        try:
            root.rmdir()
            report.deleted_paths.append(root)
        except OSError as exc:
            report.skipped_paths.append(f"{root}: {exc}")
    except OSError as exc:
        report.skipped_paths.append(f"{root}: {exc}")

    return report
