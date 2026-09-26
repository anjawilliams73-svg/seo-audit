"""
AI Readiness / AI Optimization element.
Rule-based, from crawl data only. Each content page scores 0-10.
Site score = average across sampled pages.
"""
from __future__ import annotations

import re
from typing import Any


_QUESTION_WORDS = re.compile(
    r'^(?:what|who|why|when|where|how|is|are|can|does|do|should|will)\b',
    re.I,
)


def collect(pages: list[dict], schema_data: dict) -> dict[str, Any]:
    page_schema_map = {
        r["url"]: r for r in schema_data.get("page_schema", [])
    }
    has_org_sitewide = schema_data.get("has_organization_sitewide", False)

    scored_pages = []
    for p in pages:
        if p.get("status") != 200:
            continue
        score, signals = _score_page(p, page_schema_map.get(p["url"], {}), has_org_sitewide)
        scored_pages.append({"url": p["url"], "score": score, "signals": signals})

    if not scored_pages:
        return {"score": 0, "pages": [], "common_missing": [], "note": "No 200 pages found."}

    site_score = round(sum(p["score"] for p in scored_pages) / len(scored_pages), 1)

    # find most commonly missing signals
    missing_counts: dict[str, int] = {}
    for sp in scored_pages:
        for sig, present in sp["signals"].items():
            if not present:
                missing_counts[sig] = missing_counts.get(sig, 0) + 1

    common_missing = sorted(missing_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "score": site_score,
        "pages": scored_pages,
        "common_missing": [{"signal": k, "missing_on": v} for k, v in common_missing],
    }


def _score_page(
    page: dict,
    schema_info: dict,
    has_org_sitewide: bool,
) -> tuple[float, dict[str, bool]]:
    html = page.get("body_html", "")
    signals: dict[str, bool] = {}

    # 2 pts: valid JSON-LD present
    signals["json_ld"] = schema_info.get("has_json_ld", False)

    # 1 pt: FAQ or HowTo schema
    signals["faq_or_howto"] = schema_info.get("has_faq_or_howto", False)

    # 1 pt: Organization/Person entity sitewide
    signals["org_entity"] = has_org_sitewide

    # 1 pt: at least one H2/H3 phrased as a question
    h2_h3 = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html, re.I | re.S)
    h2_h3_text = [re.sub(r'<[^>]+>', '', h).strip() for h in h2_h3]
    signals["question_heading"] = any(_QUESTION_WORDS.match(h) for h in h2_h3_text)

    # 2 pts: first paragraph under a heading answers directly (under 60 words)
    first_answer_ok = False
    heading_then_para = re.search(
        r'<h[2-4][^>]*>.*?</h[2-4]>\s*<p[^>]*>(.*?)</p>',
        html, re.I | re.S,
    )
    if heading_then_para:
        para_text = re.sub(r'<[^>]+>', '', heading_then_para.group(1)).strip()
        wc = len(para_text.split())
        first_answer_ok = 0 < wc <= 60
    signals["direct_answer"] = first_answer_ok

    # 1 pt: author name visible
    has_author = bool(
        re.search(r'"author"\s*:', html, re.I) or
        re.search(r'class=["\'][^"\']*author[^"\']*["\']', html, re.I)
    )
    signals["author_visible"] = has_author

    # 1 pt: published or updated date visible
    has_date = bool(
        re.search(r'"datePublished"\s*:', html, re.I) or
        re.search(r'"dateModified"\s*:', html, re.I) or
        re.search(r'<time[^>]+datetime', html, re.I)
    )
    signals["date_visible"] = has_date

    # 1 pt: lists or tables in content
    has_list_or_table = bool(
        re.search(r'<(?:ul|ol|table)[^>]*>', html, re.I)
    )
    signals["lists_or_tables"] = has_list_or_table

    weights = {
        "json_ld": 2,
        "faq_or_howto": 1,
        "org_entity": 1,
        "question_heading": 1,
        "direct_answer": 2,
        "author_visible": 1,
        "date_visible": 1,
        "lists_or_tables": 1,
    }
    score = sum(weights[k] for k, v in signals.items() if v)
    return score, signals
