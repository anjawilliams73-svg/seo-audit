"""
Competitor candidate generation.
Rule: suggest, never auto-select. User must confirm before any comparison runs.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx


async def suggest(
    start_url: str,
    gbp_data: dict | None,
    keyword_data: dict | None,
) -> dict[str, Any]:
    """
    Return a candidate list with reasons. The user confirms before comparison runs.
    """
    candidates: list[dict] = []
    host = urlparse(start_url).netloc.lstrip("www.")

    # source 1: nearby GBP competitors
    if gbp_data and gbp_data.get("available"):
        nearby = await _nearby_competitors(gbp_data, host)
        candidates.extend(nearby)

    # source 2: keyword overlap (from CSV if available)
    if keyword_data and keyword_data.get("mode") != "free":
        kw_comps = _keyword_competitors(keyword_data)
        for c in kw_comps:
            if not any(x["url"] == c["url"] for x in candidates):
                candidates.append(c)

    # cap at 8 suggestions
    return {
        "candidates": candidates[:8],
        "confirmed": [],
        "note": "Show these to the user and wait for confirmation before running any comparison.",
    }


async def compare(
    confirmed_urls: list[str],
    client_url: str,
    pages: list[dict],
) -> dict[str, Any]:
    """
    Crawl confirmed competitors and compare. Only runs after user confirmation.
    """
    from app.crawler.spider import crawl

    comparison: list[dict] = [{
        "url": client_url,
        "role": "client",
        "metrics": _page_metrics(pages),
    }]

    for comp_url in confirmed_urls[:3]:
        try:
            comp_pages = crawl(comp_url)
            comparison.append({
                "url": comp_url,
                "role": "competitor",
                "metrics": _page_metrics(comp_pages),
            })
        except Exception as exc:
            comparison.append({"url": comp_url, "role": "competitor", "error": str(exc)})

    gaps = _find_gaps(comparison)

    return {
        "comparison": comparison,
        "gaps_where_client_behind": gaps,
        "note": "Comparisons are only as reliable as the competitor set you chose.",
    }


def _page_metrics(pages: list[dict]) -> dict[str, Any]:
    total = len(pages)
    if total == 0:
        return {}
    avg_words = sum(p.get("word_count", 0) for p in pages) / total
    missing_titles = sum(1 for p in pages if not p.get("title"))
    missing_h1 = sum(1 for p in pages if not p.get("h1"))
    imgs_missing_alt = sum(
        sum(1 for img in p.get("images", []) if img.get("alt") is None)
        for p in pages
    )
    return {
        "pages_found": total,
        "avg_word_count": round(avg_words),
        "title_missing_pct": round(missing_titles / total * 100),
        "h1_missing_pct": round(missing_h1 / total * 100),
        "images_missing_alt": imgs_missing_alt,
    }


async def _nearby_competitors(gbp_data: dict, client_host: str) -> list[dict]:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not key:
        return []
    place_id = gbp_data.get("place_id")
    if not place_id:
        return []
    category = (gbp_data.get("types") or [""])[0]
    address = gbp_data.get("address", "")
    if not address:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # geocode the address to lat/lng
            geo = await c.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": key},
            )
            results = geo.json().get("results", [])
            if not results:
                return []
            loc = results[0]["geometry"]["location"]
            # nearby search
            nearby = await c.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{loc['lat']},{loc['lng']}",
                    "radius": "5000",
                    "type": category,
                    "key": key,
                },
            )
            items = nearby.json().get("results", [])[:8]
            candidates = []
            for item in items:
                website = item.get("website")
                if not website or client_host in website:
                    continue
                candidates.append({
                    "url": website,
                    "name": item["name"],
                    "reason": f"Same category ({category}), {item.get('vicinity', 'nearby')}",
                    "rating": item.get("rating"),
                    "reviews": item.get("user_ratings_total"),
                    "source": "nearby_search",
                })
            return candidates
    except Exception:
        return []


def _keyword_competitors(keyword_data: dict) -> list[dict]:
    # from gap CSV, extract competitor columns
    return []


def _find_gaps(comparison: list[dict]) -> list[str]:
    if len(comparison) < 2:
        return []
    client = next((c for c in comparison if c["role"] == "client"), None)
    if not client:
        return []
    gaps = []
    client_m = client.get("metrics", {})
    for comp in comparison[1:]:
        comp_m = comp.get("metrics", {})
        if comp_m.get("avg_word_count", 0) > client_m.get("avg_word_count", 0) * 1.3:
            gaps.append("Content depth: competitor pages have significantly more words on average.")
        if comp_m.get("title_missing_pct", 100) < client_m.get("title_missing_pct", 0):
            gaps.append("Title tags: more complete on competitor site.")
    return list(dict.fromkeys(gaps))
