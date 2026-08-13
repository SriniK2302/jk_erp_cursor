"""Render invoice preview HTML to PDF (A4, print styles) via Playwright."""

from __future__ import annotations


class PdfExportError(RuntimeError):
    """Raised when HTML could not be turned into a PDF (e.g. browser missing)."""


def invoice_html_list_to_pdf_bytes(*, html_documents: list[str]) -> list[bytes]:
    """
    Convert each full HTML document string to one A4 PDF using one browser session.

    Uses Microsoft Edge when available (typical on Windows), otherwise Playwright's Chromium
    (run ``playwright install chromium`` once per environment).
    """
    if not html_documents:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PdfExportError(
            "The 'playwright' package is not installed. Add it to your environment and run "
            "'playwright install chromium' (or use Edge on Windows)."
        ) from exc

    pdfs: list[bytes] = []
    margin = {"top": "0", "right": "0", "bottom": "0", "left": "0"}
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, channel="msedge")
            except Exception:
                browser = p.chromium.launch(headless=True)
            try:
                for html in html_documents:
                    page = browser.new_page()
                    try:
                        page.emulate_media(media="print")
                        page.set_content(html, wait_until="load")
                        pdfs.append(
                            page.pdf(
                                format="A4",
                                print_background=True,
                                margin=margin,
                            )
                        )
                    finally:
                        page.close()
            finally:
                browser.close()
    except Exception as exc:
        raise PdfExportError(
            "PDF rendering failed. If this is a new machine or CI image, run: playwright install chromium"
        ) from exc
    return pdfs
