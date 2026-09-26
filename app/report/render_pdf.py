"""Render the PDF report using a dedicated print-optimised Jinja2 template."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from app.report.render_html import _build_recs, _screenshots_to_b64, GUIDELINES, RECOMMENDATIONS_RAW

_TEMPLATES = Path(__file__).parent / "templates"


def render_pdf_html(
    job_id: str,
    url: str,
    pages: list[dict],
    scores: dict[str, Any],
    gbp: dict[str, Any],
    nap: dict[str, Any],
    screenshots: dict[str, Any],
    backlinks: dict[str, Any],
    psi_available: bool,
    output_path: Path,
) -> Path:
    """Render the PDF-optimised HTML template to output_path."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)))
    env.filters["tojson"] = json.dumps
    template = env.get_template("report_pdf.html")

    parsed = urlparse(url)
    site_name = parsed.netloc.lstrip("www.") or url

    elements = scores.get("elements", {})
    recommendations = _build_recs(RECOMMENDATIONS_RAW, elements)
    screenshots_b64 = _screenshots_to_b64(screenshots)

    html = template.render(
        job={
            "id": job_id,
            "url": url,
            "site_name": site_name,
            "date": datetime.utcnow().strftime("%d %B %Y"),
            "pages_crawled": len(pages),
        },
        scores=scores,
        gbp=gbp,
        nap=nap,
        screenshots=screenshots_b64,
        backlinks=backlinks,
        psi_available=psi_available,
        guidelines=GUIDELINES,
        recommendations=recommendations,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def render(
    job_id: str,
    url: str,
    pages: list[dict],
    scores: dict[str, Any],
    gbp: dict[str, Any],
    nap: dict[str, Any],
    screenshots: dict[str, Any],
    backlinks: dict[str, Any],
    psi_available: bool,
    html_path: Path,
) -> Path:
    """Render the PDF-optimised HTML then convert it to a PDF via WeasyPrint."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed. Run: pip install weasyprint")

    pdf_html_path = html_path.with_name(html_path.stem + "_pdf.html")
    render_pdf_html(
        job_id=job_id,
        url=url,
        pages=pages,
        scores=scores,
        gbp=gbp,
        nap=nap,
        screenshots=screenshots,
        backlinks=backlinks,
        psi_available=psi_available,
        output_path=pdf_html_path,
    )

    pdf_path = html_path.with_suffix(".pdf")
    pdf_bytes = WP_HTML(filename=str(pdf_html_path)).write_pdf()
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path
