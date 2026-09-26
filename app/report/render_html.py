"""Render the Jinja2 HTML report."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader


_TEMPLATES = Path(__file__).parent / "templates"
_CONFIG = Path(__file__).parents[2] / "config"

with (_CONFIG / "guidelines.json").open() as _f:
    GUIDELINES = json.load(_f)
with (_CONFIG / "recommendations.json").open() as _f:
    RECOMMENDATIONS_RAW = json.load(_f)


def _flatten_recs(raw: dict) -> dict[str, str]:
    """Turn nested recommendation dicts into element_key -> first recommendation string."""
    flat: dict[str, str] = {}
    for element, variants in raw.items():
        if isinstance(variants, dict):
            flat[element] = next(iter(variants.values()), "")
        else:
            flat[element] = str(variants)
    return flat


RECOMMENDATIONS = _flatten_recs(RECOMMENDATIONS_RAW)


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
    output_path: Path,
) -> Path:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)))
    env.filters["tojson"] = json.dumps
    template = env.get_template("report.html")

    parsed = urlparse(url)
    site_name = parsed.netloc.lstrip("www.") or url

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
        screenshots=screenshots,
        backlinks=backlinks,
        psi_available=psi_available,
        guidelines=GUIDELINES,
        recommendations=RECOMMENDATIONS,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
