"""Find spreadsheet files with identical content (SHA-256 file signature)."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#from tkinter import Tk, TclError, filedialog


ProgressCallback = Callable[[str, int, int | None, str], None]
SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
_READ_CHUNK = 1024 * 1024


@dataclass
class SimilarFileMatch:
    file_a: Path
    file_b: Path
    overall_similarity: float  # 1.0 when byte-identical (same SHA-256)
    sha256_hex: str


@dataclass
class SimilarFilesReport:
    root: Path
    threshold: float
    scanned_files: int = 0
    spreadsheet_files: int = 0
    skipped_paths: list[str] = field(default_factory=list)
    matches: list[SimilarFileMatch] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


@dataclass
class SimilarToReferenceReport:
    reference_file: Path
    root: Path
    threshold: float
    scanned_files: int = 0
    spreadsheet_files: int = 0
    skipped_paths: list[str] = field(default_factory=list)
    matches: list[SimilarFileMatch] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(_READ_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def choose_spreadsheet_file() -> Path | None:
    """Open native file picker for spreadsheet files."""
    try:
        from tkinter import Tk, TclError, filedialog
    except ImportError as exc:
        raise RuntimeError(
            "File picker requires a desktop environment with tkinter; "
            "not available on this server."
        ) from exc

    try:
        picker_root = Tk()
        picker_root.withdraw()
        picker_root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Select reference spreadsheet file",
            filetypes=[
                ("Spreadsheet files", "*.xlsx *.xlsm *.xltx *.xltm"),
                ("All files", "*.*"),
            ],
        )
        picker_root.destroy()
    except TclError as exc:
        raise RuntimeError("Unable to launch file picker.") from exc

    if not selected:
        return None
    return Path(selected)


def is_supported_spreadsheet(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_similar_to_reference_file(
    reference_file: Path,
    root: Path,
    threshold: float = 0.95,
    progress_callback: ProgressCallback | None = None,
) -> SimilarToReferenceReport:
    """
    Find spreadsheet files under ``root`` whose bytes match the reference file
    (same SHA-256). Only a report is returned; nothing is moved or changed.
    """
    reference_file = reference_file.resolve()
    root = root.resolve()
    report = SimilarToReferenceReport(
        reference_file=reference_file,
        root=root,
        threshold=threshold,
    )

    if not reference_file.exists() or not reference_file.is_file():
        raise ValueError(f"Reference file not found: {reference_file}")
    if not is_supported_spreadsheet(reference_file):
        raise ValueError("Reference file must be an Excel spreadsheet (.xlsx/.xlsm/.xltx/.xltm).")
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Scan folder not found: {root}")

    def notify(phase: str, current: int, total: int | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(phase, current, total, message)

    notify("profiling", 0, 1, "Hashing reference file...")
    try:
        reference_digest = _sha256_hex(reference_file)
    except OSError as exc:
        raise ValueError(f"Cannot read reference file: {reference_file}") from exc
    notify("profiling", 1, 1, "Reference hashed.")

    all_files = sorted(
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )
    total_files = len(all_files)
    notify("collecting", 0, total_files, "Listing files under scan folder...")

    candidates: list[Path] = []
    for index, path in enumerate(all_files, start=1):
        report.scanned_files += 1
        if index % 100 == 0 or index == total_files:
            notify(
                "collecting",
                index,
                total_files,
                f"Listed {index}/{total_files} files...",
            )

        if path.resolve() == reference_file:
            continue
        if not is_supported_spreadsheet(path):
            continue
        candidates.append(path)

    total_candidates = len(candidates)
    notify(
        "comparing",
        0,
        total_candidates,
        f"Hashing {total_candidates} spreadsheets...",
    )

    for index, path in enumerate(candidates, start=1):
        report.spreadsheet_files += 1
        try:
            digest = _sha256_hex(path)
        except OSError as exc:
            report.skipped_paths.append(f"{path}: {exc}")
        else:
            if digest == reference_digest and 1.0 >= threshold:
                report.matches.append(
                    SimilarFileMatch(
                        file_a=reference_file,
                        file_b=path,
                        overall_similarity=1.0,
                        sha256_hex=digest,
                    )
                )

        if index % 25 == 0 or index == total_candidates:
            notify(
                "comparing",
                index,
                total_candidates,
                f"Hashed {index}/{total_candidates} spreadsheets...",
            )

    report.matches.sort(key=lambda item: str(item.file_b).lower())
    notify("done", len(report.matches), len(report.matches), "Similar file scan completed.")
    return report


def find_similar_spreadsheet_files(
    root: Path,
    threshold: float = 0.95,
    progress_callback: ProgressCallback | None = None,
) -> SimilarFilesReport:
    """
    Find spreadsheet pairs with identical file bytes (same SHA-256).

    This routine only reads files; it does not move or modify anything.
    """
    root = root.resolve()
    report = SimilarFilesReport(root=root, threshold=threshold)

    def notify(phase: str, current: int, total: int | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(phase, current, total, message)

    all_files = sorted(
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )
    total_files = len(all_files)
    notify("collecting", 0, total_files, "Scanning files...")

    spreadsheet_paths: list[Path] = []
    for index, path in enumerate(all_files, start=1):
        report.scanned_files += 1
        notify("collecting", index, total_files, f"Scanned {index}/{total_files} files...")

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        spreadsheet_paths.append(path)

    total_paths = len(spreadsheet_paths)
    notify("comparing", 0, total_paths, "Hashing spreadsheets...")

    digest_to_paths: defaultdict[str, list[Path]] = defaultdict(list)
    for index, path in enumerate(spreadsheet_paths, start=1):
        report.spreadsheet_files += 1
        try:
            digest = _sha256_hex(path)
        except OSError as exc:
            report.skipped_paths.append(f"{path}: {exc}")
        else:
            digest_to_paths[digest].append(path)

        if index % 25 == 0 or index == total_paths:
            notify(
                "comparing",
                index,
                total_paths,
                f"Hashed {index}/{total_paths} spreadsheets...",
            )

    if 1.0 >= threshold:
        for digest, paths in digest_to_paths.items():
            if len(paths) < 2:
                continue
            paths_sorted = sorted(paths, key=lambda p: str(p).lower())
            m = len(paths_sorted)
            for i in range(m):
                for j in range(i + 1, m):
                    report.matches.append(
                        SimilarFileMatch(
                            file_a=paths_sorted[i],
                            file_b=paths_sorted[j],
                            overall_similarity=1.0,
                            sha256_hex=digest,
                        )
                    )

    report.matches.sort(key=lambda item: (str(item.file_a).lower(), str(item.file_b).lower()))
    notify("done", len(report.matches), len(report.matches), "Similar file scan completed.")
    return report
