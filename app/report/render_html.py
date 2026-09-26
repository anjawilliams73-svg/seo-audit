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


def _build_recs(raw: dict, elements: dict[str, dict]) -> dict[str, str]:
    """Pick the right recommendation variant per element and fill {count}/{types} placeholders."""
    result: dict[str, str] = {}
    for key, variants in raw.items():
        el = elements.get(key, {})
        details = el.get("details", {})
        if not isinstance(variants, dict):
            result[key] = str(variants)
            continue
        chosen = ""
        # Pick most critical variant based on actual details
        if key == "title_tags":
            if details.get("missing", 0):
                chosen = variants.get("missing", "").replace("{count}", str(details["missing"]))
            elif details.get("too_long", 0):
                chosen = variants.get("too_long", "").replace("{count}", str(details["too_long"]))
            elif details.get("too_short", 0):
                chosen = variants.get("too_short", "").replace("{count}", str(details["too_short"]))
            elif details.get("duplicates", 0):
                chosen = variants.get("duplicate", "").replace("{count}", str(details["duplicates"]))
        elif key == "meta_descriptions":
            if details.get("missing", 0):
                chosen = variants.get("missing", "").replace("{count}", str(details["missing"]))
        elif key == "heading_tags":
            if details.get("missing_h1", 0):
                chosen = variants.get("missing_h1", "").replace("{count}", str(details["missing_h1"]))
            elif details.get("multiple_h1", 0):
                chosen = variants.get("multiple_h1", "").replace("{count}", str(details["multiple_h1"]))
            elif details.get("duplicate_h1", 0):
                chosen = variants.get("duplicate_h1", "").replace("{count}", str(details["duplicate_h1"]))
        elif key == "image_alts":
            if details.get("missing_alt", 0):
                chosen = variants.get("missing_alt", "").replace("{count}", str(details["missing_alt"]))
        elif key == "broken_links":
            count = details.get("broken_count", details.get("count", 0))
            chosen = variants.get("404", "").replace("{count}", str(count))
        elif key == "url_redirects":
            count = details.get("redirects_302", details.get("count", 0))
            chosen = variants.get("302", "").replace("{count}", str(count))
        elif key == "schema":
            missing = details.get("missing_types", [])
            types_str = ", ".join(missing) if missing else "LocalBusiness, FAQPage"
            chosen = variants.get("missing_types", "").replace("{types}", types_str)
        elif key == "social_media":
            chosen = next(iter(variants.values()), "")
        else:
            # Generic: pick first variant, replace any {count} with a sensible value
            v = next(iter(variants.values()), "")
            count = details.get("missing", details.get("broken_count", details.get("count", 0)))
            chosen = v.replace("{count}", str(count))
        result[key] = chosen
    return result


def _screenshots_to_b64(screenshots: dict) -> dict:
    """Convert screenshot file paths to base64 data URIs for embedding in HTML."""
    import base64
    updated = dict(screenshots)
    shots = []
    for s in screenshots.get("screenshots", []):
        s = dict(s)
        path = s.get("path")
        if path:
            try:
                data = Path(path).read_bytes()
                s["data_uri"] = "data:image/png;base64," + base64.b64encode(data).decode()
            except Exception:
                pass
        shots.append(s)
    updated["screenshots"] = shots
    return updated


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
