"""
Element score functions. Each returns a dict:
  { "score": 0-10, "details": {...}, "affected_urls": [...] }

Elements with "Not available" data return score=None and are excluded from averages.
"""
from __future__ import annotations

from typing import Any

from .weights import CATEGORY_WEIGHTS, ELEMENTS


# ── issue rate helper ──────────────────────────────────────────────────────

def _issue_rate_score(affected: int, total: int) -> int:
    if total == 0:
        return 10
    rate = affected / total
    if rate == 0:
        return 10
    if rate < 0.05:
        return 8
    if rate < 0.15:
        return 6
    if rate < 0.30:
        return 4
    if rate < 0.60:
        return 3
    return 1


# ── on-site elements ──────────────────────────────────────────────────────

def score_title_tags(pages: list[dict]) -> dict[str, Any]:
    html_pages = [p for p in pages if p.get("status") == 200]
    total = len(html_pages)
    missing = [p["url"] for p in html_pages if not p.get("title")]
    too_long = [p["url"] for p in html_pages if p.get("title") and len(p["title"]) > 60]
    too_short = [p["url"] for p in html_pages if p.get("title") and len(p["title"]) < 30]
    titles = [p.get("title", "") for p in html_pages]
    duplicates = [p["url"] for p in html_pages if titles.count(p.get("title", "")) > 1 and p.get("title")]

    issues = missing + too_long + too_short + duplicates
    score = _issue_rate_score(len(set(issues)), total)
    return {
        "score": score,
        "details": {
            "total": total,
            "missing": len(missing),
            "too_long": len(too_long),
            "too_short": len(too_short),
            "duplicates": len(duplicates),
        },
        "affected_urls": list(set(missing + too_long)),
    }


def score_meta_descriptions(pages: list[dict]) -> dict[str, Any]:
    html_pages = [p for p in pages if p.get("status") == 200]
    total = len(html_pages)
    missing = [p["url"] for p in html_pages if not p.get("meta_description")]
    too_long = [p["url"] for p in html_pages if p.get("meta_description") and len(p["meta_description"]) > 155]
    score = _issue_rate_score(len(missing) + len(too_long), total)
    return {
        "score": score,
        "details": {"total": total, "missing": len(missing), "too_long": len(too_long)},
        "affected_urls": missing,
    }


def score_heading_tags(pages: list[dict]) -> dict[str, Any]:
    html_pages = [p for p in pages if p.get("status") == 200]
    total = len(html_pages)
    missing_h1 = [p["url"] for p in html_pages if not p.get("h1")]
    multiple_h1 = [p["url"] for p in html_pages if len(p.get("h1", [])) > 1]
    h1_texts = [p["h1"][0] if p.get("h1") else "" for p in html_pages]
    dup_h1 = [p["url"] for p in html_pages if p.get("h1") and h1_texts.count(p["h1"][0]) > 1]
    issues = set(missing_h1 + multiple_h1 + dup_h1)
    score = _issue_rate_score(len(issues), total)
    return {
        "score": score,
        "details": {
            "total": total,
            "missing_h1": len(missing_h1),
            "multiple_h1": len(multiple_h1),
            "duplicate_h1": len(dup_h1),
        },
        "affected_urls": list(issues),
    }


def score_image_alts(pages: list[dict]) -> dict[str, Any]:
    all_imgs = sum(len(p.get("images", [])) for p in pages)
    missing_alt = sum(
        sum(1 for img in p.get("images", []) if img.get("alt") is None)
        for p in pages
    )
    pages_with_missing = [
        p["url"] for p in pages
        if any(img.get("alt") is None for img in p.get("images", []))
    ]
    score = _issue_rate_score(missing_alt, all_imgs) if all_imgs else 10
    return {
        "score": score,
        "details": {"total_images": all_imgs, "missing_alt": missing_alt},
        "affected_urls": pages_with_missing,
    }


def score_page_load_speed(psi_data: dict) -> dict[str, Any]:
    if not psi_data:
        return {"score": None, "details": {"note": "Not available — PageSpeed API not reached."}, "affected_urls": []}
    homepage_result = next(iter(psi_data.values()), {})
    if homepage_result.get("error"):
        return {"score": None, "details": {"note": f"PSI error: {homepage_result['error']}"}, "affected_urls": []}
    lcp = homepage_result.get("lcp", {})
    lcp_score = lcp.get("score")
    if lcp_score is None:
        element_score = None
    elif lcp_score >= 0.9:
        element_score = 10
    elif lcp_score >= 0.5:
        element_score = 6
    else:
        element_score = 3
    return {
        "score": element_score,
        "details": {
            "lcp": lcp.get("value"),
            "performance": homepage_result.get("performance"),
            "opportunities": homepage_result.get("opportunities", [])[:3],
        },
        "affected_urls": [],
    }


def score_schema(schema_data: dict) -> dict[str, Any]:
    missing = schema_data.get("pages_missing_schema", [])
    total = len(schema_data.get("page_schema", [])) or 1
    score = _issue_rate_score(len(missing), total)
    # bonus if org schema present
    if schema_data.get("has_organization_sitewide"):
        score = min(10, score + 1)
    return {
        "score": score,
        "details": {
            "types_found": schema_data.get("sitewide_types", []),
            "missing_types": schema_data.get("missing_types", []),
            "pages_without_schema": len(missing),
        },
        "affected_urls": missing,
    }


def score_ai_optimization(ai_data: dict) -> dict[str, Any]:
    s = ai_data.get("score", 0)
    # ai_data score is 0-10 already
    return {
        "score": round(s),
        "details": {
            "site_score": s,
            "common_missing": ai_data.get("common_missing", []),
        },
        "affected_urls": [],
    }


def score_internal_linking(pages: list[dict]) -> dict[str, Any]:
    html_pages = [p for p in pages if p.get("status") == 200]
    total = len(html_pages)
    no_internal = [p["url"] for p in html_pages if p.get("internal_links", 0) == 0]
    score = _issue_rate_score(len(no_internal), total)
    avg_links = (sum(p.get("internal_links", 0) for p in html_pages) / total) if total else 0
    return {
        "score": score,
        "details": {"avg_internal_links": round(avg_links, 1), "pages_with_none": len(no_internal)},
        "affected_urls": no_internal,
    }


def score_content(pages: list[dict]) -> dict[str, Any]:
    html_pages = [p for p in pages if p.get("status") == 200]
    thin = [p["url"] for p in html_pages if p.get("word_count", 0) < 300]
    total = len(html_pages)
    score = _issue_rate_score(len(thin), total)
    avg_words = (sum(p.get("word_count", 0) for p in html_pages) / total) if total else 0
    return {
        "score": score,
        "details": {"avg_word_count": round(avg_words), "thin_pages": len(thin)},
        "affected_urls": thin,
    }


def score_keyword_focus(keyword_data: dict) -> dict[str, Any]:
    pages = keyword_data.get("page_keywords", [])
    if not pages:
        return {"score": None, "details": {"note": "Not available."}, "affected_urls": []}
    total = len(pages)
    missing_focus = [
        p["url"] for p in pages
        if not any(p.get("focus", {}).values())
    ]
    score = _issue_rate_score(len(missing_focus), total)
    return {
        "score": score,
        "details": {"pages_checked": total, "pages_missing_focus": len(missing_focus)},
        "affected_urls": missing_focus,
    }


def score_url_structure(pages: list[dict]) -> dict[str, Any]:
    import re
    html_pages = [p for p in pages if p.get("status") == 200]
    bad = [
        p["url"] for p in html_pages
        if re.search(r'[?=&]{2,}|[A-Z]|%[0-9A-F]{2}', p["url"])
    ]
    total = len(html_pages)
    score = _issue_rate_score(len(bad), total)
    return {
        "score": score,
        "details": {"total": total, "poor_url_structure": len(bad)},
        "affected_urls": bad,
    }


def score_nofollow(pages: list[dict]) -> dict[str, Any]:
    total_links = sum(p.get("external_links", 0) for p in pages)
    total_nofollow = sum(p.get("nofollow_links", 0) for p in pages)
    if total_links == 0:
        return {"score": 10, "details": {"total_external": 0, "nofollow": 0}, "affected_urls": []}
    nofollow_rate = total_nofollow / total_links
    score = 8 if nofollow_rate < 0.5 else 5
    return {
        "score": score,
        "details": {"total_external": total_links, "nofollow": total_nofollow},
        "affected_urls": [],
    }


def score_code_validation(validation_result: dict | None) -> dict[str, Any]:
    if not validation_result:
        return {"score": None, "details": {"note": "Not available — W3C validator not reached."}, "affected_urls": []}
    errors = validation_result.get("errors", 0)
    warnings = validation_result.get("warnings", 0)
    if errors == 0:
        score = 10
    elif errors < 5:
        score = 7
    elif errors < 15:
        score = 5
    else:
        score = 3
    return {
        "score": score,
        "details": {"errors": errors, "warnings": warnings},
        "affected_urls": [],
    }


# ── indexing elements ─────────────────────────────────────────────────────

def score_indexing_optimization(indexing_data: dict) -> dict[str, Any]:
    has_robots = indexing_data.get("robots_found", False)
    has_sitemap = indexing_data.get("sitemap_count", 0) > 0
    score = 10
    notes = []
    if not has_robots:
        score -= 3
        notes.append("No robots.txt found.")
    if not has_sitemap:
        score -= 3
        notes.append("No sitemap found.")
    return {
        "score": max(0, score),
        "details": {"has_robots": has_robots, "has_sitemap": has_sitemap, "notes": notes},
        "affected_urls": [],
    }


def score_page_exclusions(indexing_data: dict) -> dict[str, Any]:
    noindex = indexing_data.get("noindex_pages", [])
    total = indexing_data.get("total_crawled", 1)
    note = f"{len(noindex)} pages have noindex directives."
    score = 8 if noindex else 10
    return {
        "score": score,
        "details": {"noindex_count": len(noindex), "note": note},
        "affected_urls": noindex,
    }


def score_page_inclusions(indexing_data: dict) -> dict[str, Any]:
    not_in_sitemap = indexing_data.get("crawled_not_in_sitemap", [])
    total = indexing_data.get("total_crawled", 1)
    score = _issue_rate_score(len(not_in_sitemap), total)
    return {
        "score": score,
        "details": {"pages_not_in_sitemap": len(not_in_sitemap)},
        "affected_urls": not_in_sitemap[:20],
    }


def score_url_redirects(indexing_data: dict) -> dict[str, Any]:
    r302 = indexing_data.get("redirects_302", [])
    r301 = indexing_data.get("redirects_301", [])
    total = len(r301) + len(r302)
    score = _issue_rate_score(len(r302), total) if total else 10
    return {
        "score": score,
        "details": {"redirects_301": len(r301), "redirects_302": len(r302)},
        "affected_urls": r302,
    }


def score_duplicate_content(pages: list[dict]) -> dict[str, Any]:
    try:
        from simhash import Simhash
        import re
        fingerprints: list[tuple[int, str]] = []
        for p in pages:
            text = re.sub(r'<[^>]+>', ' ', p.get("body_html", ""))
            h = Simhash(text).value
            fingerprints.append((h, p["url"]))
        duplicates: list[str] = []
        for i, (h1, u1) in enumerate(fingerprints):
            for h2, u2 in fingerprints[i+1:]:
                if bin(h1 ^ h2).count('1') <= 3:
                    duplicates.append(u2)
        total = len(pages)
        score = _issue_rate_score(len(duplicates), total)
        return {
            "score": score,
            "details": {"duplicate_pages": len(duplicates), "total": total},
            "affected_urls": duplicates[:20],
        }
    except Exception:
        return {"score": None, "details": {"note": "Not available — simhash library error."}, "affected_urls": []}


def score_broken_links(indexing_data: dict, total_pages: int) -> dict[str, Any]:
    broken = indexing_data.get("broken_links", [])
    score = _issue_rate_score(len(broken), total_pages)
    return {
        "score": max(1, score) if broken else 10,
        "details": {"broken_count": len(broken)},
        "affected_urls": broken,
    }


# ── linking/social elements ───────────────────────────────────────────────

def score_linking_root_domains(backlink_data: dict) -> dict[str, Any]:
    if not backlink_data.get("available"):
        return {"score": None, "details": {"note": backlink_data.get("note", "Not available.")}, "affected_urls": []}
    domains = backlink_data.get("linking_domains", 0) or 0
    score = min(10, max(1, domains // 10))
    return {
        "score": score,
        "details": {
            "linking_domains": domains,
            "is_estimate": True,
            "source": "Common Crawl",
        },
        "affected_urls": [],
    }


def score_inbound_links(backlink_data: dict) -> dict[str, Any]:
    if not backlink_data.get("available"):
        return {"score": None, "details": {"note": "Not available."}, "affected_urls": []}
    urls = backlink_data.get("inbound_urls", 0) or 0
    score = min(10, max(1, urls // 50))
    return {
        "score": score,
        "details": {"inbound_urls": urls, "is_estimate": True, "source": "Common Crawl"},
        "affected_urls": [],
    }


def score_authority_trust(backlink_data: dict) -> dict[str, Any]:
    # DA/PA not available for free — always "Not available"
    return {
        "score": None,
        "details": {
            "note": "Domain Authority / Trust metrics are not available for free. "
                    "Moz DA, Ahrefs DR, and similar scores require paid subscriptions."
        },
        "affected_urls": [],
    }


def score_social_media(social_data: dict) -> dict[str, Any]:
    profiles = social_data.get("profiles", [])
    found = [p for p in profiles if p.get("status") != "not_found"]
    inactive = [p for p in profiles if p.get("status") == "inactive"]
    score = 10
    if not found:
        score = 2
    elif inactive:
        score = max(4, 10 - len(inactive) * 2)
    elif len(found) < 2:
        score = 5
    return {
        "score": score,
        "details": {
            "profiles_found": len(found),
            "inactive": len(inactive),
            "platforms": [p["platform"] for p in profiles if p.get("url")],
        },
        "affected_urls": [],
    }


def score_competitive_link_comparison(backlink_data: dict) -> dict[str, Any]:
    if not backlink_data.get("available"):
        return {"score": None, "details": {"note": "Not available without confirmed competitor comparison."}, "affected_urls": []}
    return {"score": 5, "details": {"note": "Competitor backlink comparison requires confirmed competitors."}, "affected_urls": []}


def score_gbp(gbp_data: dict) -> dict[str, Any]:
    if not gbp_data or not gbp_data.get("available"):
        return {"score": 0, "details": {"note": "No GBP profile found or provided."}, "affected_urls": []}
    # base 5 for existing + up to 5 for completeness
    score = 5
    data = gbp_data
    if data.get("phone"):
        score += 1
    if data.get("hours"):
        score += 1
    if data.get("website"):
        score += 1
    if (data.get("review_count") or 0) > 10:
        score += 1
    if (data.get("photos") or 0) > 0:
        score += 1
    return {
        "score": min(10, score),
        "details": {
            "name": data.get("name"),
            "rating": data.get("rating"),
            "review_count": data.get("review_count"),
            "photos": data.get("photos"),
        },
        "affected_urls": [],
    }


def score_nap(nap_data: dict) -> dict[str, Any]:
    return {
        "score": nap_data.get("score", 0),
        "details": {
            "site_nap": nap_data.get("site"),
            "mismatches": nap_data.get("mismatches", []),
        },
        "affected_urls": [],
    }


# ── aggregate ──────────────────────────────────────────────────────────────

def aggregate(element_scores: dict[str, dict]) -> dict[str, Any]:
    def cat_score(keys: list[str]) -> float | None:
        valid = [element_scores[k]["score"] for k in keys if element_scores.get(k, {}).get("score") is not None]
        return round(sum(valid) / len(valid) * 10, 1) if valid else None

    on_site = cat_score(ELEMENTS["on_site"])
    indexing = cat_score(ELEMENTS["indexing"])
    linking = cat_score(ELEMENTS["linking_social"])

    overall: float | None = None
    parts = [(on_site, CATEGORY_WEIGHTS["on_site"]), (indexing, CATEGORY_WEIGHTS["indexing"]), (linking, CATEGORY_WEIGHTS["linking_social"])]
    valid_parts = [(s, w) for s, w in parts if s is not None]
    if valid_parts:
        total_w = sum(w for _, w in valid_parts)
        overall = round(sum(s * w for s, w in valid_parts) / total_w, 1)

    fix_first = [
        {"element": k, "score": v["score"], "category": _element_category(k)}
        for k, v in element_scores.items()
        if v.get("score") is not None and v["score"] <= 3
    ]
    fix_first.sort(key=lambda x: (CATEGORY_WEIGHTS.get(x["category"], 0), x["score"]), reverse=True)

    return {
        "overall": overall,
        "on_site": on_site,
        "indexing": indexing,
        "linking_social": linking,
        "elements": element_scores,
        "fix_first": fix_first,
    }


def _element_category(element: str) -> str:
    for cat, elems in ELEMENTS.items():
        if element in elems:
            return cat
    return "on_site"
