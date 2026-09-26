"""Convert the HTML report to PDF using WeasyPrint."""
from __future__ import annotations

from pathlib import Path


def render(html_path: Path) -> Path:
    """Convert html_path to a PDF at the same location with .pdf extension."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed. Run: pip install weasyprint")

    pdf_path = html_path.with_suffix(".pdf")
    pdf_bytes = WP_HTML(filename=str(html_path)).write_pdf()
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path
