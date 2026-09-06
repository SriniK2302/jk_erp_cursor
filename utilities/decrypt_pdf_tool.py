"""Decrypt a password-protected PDF into a plain, unprotected copy.

Uses pikepdf to open the PDF with the supplied password and write a new,
unencrypted file. The original file is never modified — this works even
for digitally signed PDFs where in-place security removal is blocked,
since we're only writing a fresh copy, not editing the signed original.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf

PDF_FILETYPES = [
    ("PDF files", "*.pdf"),
    ("All files", "*.*"),
]


def choose_pdf_file() -> Path | None:
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
            title="Select password-protected PDF",
            filetypes=PDF_FILETYPES,
        )
        root.destroy()
    except TclError as exc:
        raise RuntimeError("Unable to launch file picker.") from exc
    if not selected:
        return None
    return Path(selected)


def decrypt_pdf(path: Path, password: str) -> Path:
    """Writes a decrypted copy of ``path`` next to it and returns its Path.

    Raises pikepdf.PasswordError if the password is wrong.
    """
    output_path = path.with_name(f"{path.stem}_decrypted{path.suffix}")
    with pikepdf.open(path, password=password) as pdf:
        pdf.save(output_path)
    return output_path
