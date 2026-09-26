"""
Orchestrates the full audit pipeline.
Runs: crawl → collectors → scoring → report.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any


async def run(
    job_id: str,
    url: str,
    gbp_url: str | None = None,
    keyword_csv_content: bytes | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    from app.crawler.spider import crawl
    from app.collectors import (
        pagespeed, indexing, schema as schema_collector,
        backlinks, social, ai_readiness, screenshots as sc_mod,
        gbp as gbp_mod, nap as nap_mod, keywords as kw_mod,
    )
    from app.scoring import rules
    from app.report import render_html, render_pdf

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix=f"audit_{job_id}_"))

    # ── 1. Crawl ────────────────────────────────────────────────────────────
    pages = await asyncio.get_event_loop().run_in_executor(None, crawl, url)

    # ── 2. Collect (run async tasks in parallel) ────────────────────────────
    psi_urls = [p["url"] for p in pages[:6] if p.get("status") == 200]

    schema_data = schema_collector.collect(pages)
    ai_data = ai_readiness.collect(pages, schema_data)

    psi_task = pagespeed.collect(psi_urls)
    indexing_task = indexing.collect(url, pages)
    backlinks_task = backlinks.collect(url)
    social_task = social.collect(pages)
    screenshots_task = sc_mod.collect(url)

    # extract business name from schema for GBP lookup
    biz_name: str | None = None
    for org in schema_data.get("page_schema", []):
        if org.get("has_organization_or_person"):
            break

    gbp_task = gbp_mod.collect(gbp_url, url, biz_name)

    (
        psi_data,
        indexing_data,
        backlinks_data,
        social_data,
        screenshots_data,
        gbp_data,
    ) = await asyncio.gather(
        psi_task, indexing_task, backlinks_task,
        social_task, screenshots_task, gbp_task,
    )

    nap_data = nap_mod.collect(pages, gbp_data, schema_data)

    # keywords
    if keyword_csv_content:
        keyword_data = kw_mod.parse_keyword_csv(keyword_csv_content)
    else:
        keyword_data = await kw_mod.collect_free(pages)

    # W3C validation (best effort, homepage only)
    validation_data = await _w3c_validate(url)

    # ── 3. Score ────────────────────────────────────────────────────────────
    element_scores: dict[str, dict] = {
        "keyword_focus":              rules.score_keyword_focus(keyword_data),
        "url_structure":              rules.score_url_structure(pages),
        "title_tags":                 rules.score_title_tags(pages),
        "meta_descriptions":          rules.score_meta_descriptions(pages),
        "heading_tags":               rules.score_heading_tags(pages),
        "content":                    rules.score_content(pages),
        "internal_linking":           rules.score_internal_linking(pages),
        "image_alts":                 rules.score_image_alts(pages),
        "nofollow":                   rules.score_nofollow(pages),
        "page_load_speed":            rules.score_page_load_speed(psi_data),
        "schema":                     rules.score_schema(schema_data),
        "ai_optimization":            rules.score_ai_optimization(ai_data),
        "code_validation":            rules.score_code_validation(validation_data),
        "indexing_optimization":      rules.score_indexing_optimization(indexing_data),
        "page_exclusions":            rules.score_page_exclusions(indexing_data),
        "page_inclusions":            rules.score_page_inclusions(indexing_data),
        "url_redirects":              rules.score_url_redirects(indexing_data),
        "duplicate_content":          rules.score_duplicate_content(pages),
        "broken_links":               rules.score_broken_links(indexing_data, len(pages)),
        "linking_root_domains":       rules.score_linking_root_domains(backlinks_data),
        "inbound_followed_links":     rules.score_inbound_links(backlinks_data),
        "authority_trust":            rules.score_authority_trust(backlinks_data),
        "social_media":               rules.score_social_media(social_data),
        "competitive_link_comparison":rules.score_competitive_link_comparison(backlinks_data),
        "google_business_profile":    rules.score_gbp(gbp_data),
        "nap":                        rules.score_nap(nap_data),
    }

    scores = rules.aggregate(element_scores)

    # ── 4. Report ────────────────────────────────────────────────────────────
    html_path = output_dir / f"{job_id}.html"
    render_html.render(
        job_id=job_id,
        url=url,
        pages=pages,
        scores=scores,
        gbp=gbp_data,
        nap=nap_data,
        screenshots=screenshots_data,
        backlinks=backlinks_data,
        psi_available=bool(psi_data and not next(iter(psi_data.values()), {}).get("error")),
        output_path=html_path,
    )

    try:
        pdf_path = render_pdf.render(html_path)
        pdf_path_str = str(pdf_path)
    except Exception:
        pdf_path_str = None

    return {
        "job_id": job_id,
        "status": "complete",
        "scores": scores,
        "html_path": str(html_path),
        "pdf_path": pdf_path_str,
        "pages_crawled": len(pages),
        "gbp": gbp_data,
        "nap": nap_data,
        "social": social_data,
        "indexing": indexing_data,
        "schema": schema_data,
        "ai_readiness": ai_data,
        "keywords": keyword_data,
        "backlinks": backlinks_data,
        "screenshots": screenshots_data,
    }


async def _w3c_validate(url: str) -> dict | None:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://validator.w3.org/nu/",
                params={"doc": url, "out": "json"},
                headers={"User-Agent": "SEOAuditBot/1.0"},
            )
            if r.status_code == 200:
                data = r.json()
                messages = data.get("messages", [])
                errors = sum(1 for m in messages if m.get("type") == "error")
                warnings = sum(1 for m in messages if m.get("type") == "warning" or m.get("subType") == "warning")
                return {"errors": errors, "warnings": warnings}
    except Exception:
        pass
    return None
