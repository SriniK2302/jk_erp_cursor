"""Save bulk invoice PDF ZIP exports under MEDIA_ROOT for reliable download."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def bulk_invoice_export_dir() -> Path:
    root = Path(settings.MEDIA_ROOT) / "bulk_invoice_exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_bulk_invoice_zip(*, pdf_parts: list[bytes], safe_names: list[str]) -> tuple[str, Path]:
    """
    Write invoice PDFs into a timestamped ZIP under media/bulk_invoice_exports/.
    Returns (relative path under MEDIA_ROOT, absolute path).
    """
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"invoice_pdfs_{stamp}.zip"
    export_dir = bulk_invoice_export_dir()
    zip_path = export_dir / zip_name
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_name, pdf_bytes in zip(safe_names, pdf_parts, strict=True):
            zf.writestr(f"{safe_name}.pdf", pdf_bytes)
    zip_path.write_bytes(buf.getvalue())
    rel = zip_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    return rel, zip_path
