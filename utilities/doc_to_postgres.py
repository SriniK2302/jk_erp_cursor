"""
Import bank transaction rows from a PDF statement into PostgreSQL.

Companion to excel_to_postgres.py, for PDF-format bank statements instead of
Excel/CSV. Kept as a separate module for now; will be merged/wired in later.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path

DOC_FILETYPES = [
    ("CSV files", "*.csv"),
    ("Excel workbooks", "*.xlsx *.xlsm *.xltx *.xltm *.xls"),
    ("PDF files", "*.pdf"),
    ("All files", "*.*"),
]

DOC_DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
]


def parse_doc_date(s: str):
    """
    Parse a date string using any format in DOC_DATE_FORMATS. Returns a
    date, or None if it doesn't match any known format.
    """
    s = s.strip()
    for fmt in DOC_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def build_output_source_ac_name(date_strings: list[str]) -> str:
    """
    Orchestrator: parses each date string, finds the last (max) date.
    More parts will be added as later extraction methods are built.
    """
    parsed = [parse_doc_date(s) for s in date_strings]
    parsed = [d for d in parsed if d is not None]
    if not parsed:
        return ""
    last_date = max(parsed)
    return ""

def choose_doc_file() -> Path | None:
    try:
        from tkinter import Tk, TclError, filedialog
    except ImportError as exc:
        raise RuntimeError(
            "File picker requires a desktop environment with tkinter; "
            "not available on this server."
        ) from exc

    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Select file to import",
            filetypes=DOC_FILETYPES,
        )
        root.destroy()
    except TclError as exc:
        raise RuntimeError("Unable to launch file picker.") from exc
    if not selected:
        return None
    return Path(selected)
