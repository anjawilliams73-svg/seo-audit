"""
Keyword analysis module — two modes: with CSV (full) and without (free only).
Free mode: YAKE extraction + Google Autocomplete expansion.
"""
from __future__ import annotations

import io
import re
from typing import Any

import httpx


# ── free mode ─────────────────────────────────────────────────────────────

async def collect_free(pages: list[dict]) -> dict[str, Any]:
    """Extract and expand keywords without any CSV uploads."""
    page_keywords: list[dict] = []

    for p in pages:
        if p.get("status") != 200:
            continue
        kws = _yake_extract(p.get("body_html", ""), top_n=10)
        focus = _keyword_focus(p, kws[0] if kws else "")
        page_keywords.append({
            "url": p["url"],
            "top_keywords": kws,
            "focus": focus,
        })

    # aggregate seeds for autocomplete
    seeds: list[str] = []
    for pk in page_keywords[:3]:
        seeds.extend(pk["top_keywords"][:3])

    expansions: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=10) as c:
        for seed in seeds[:6]:
            expansions[seed] = await _autocomplete(seed, c)

    cannibalization = _detect_cannibalization(page_keywords)

    return {
        "mode": "free",
        "volume_available": False,
        "page_keywords": page_keywords,
        "autocomplete_expansions": expansions,
        "cannibalization": cannibalization,
        "note": "Search volume not available for free. Numbers from CSV uploads only.",
    }


def _yake_extract(html: str, top_n: int = 10) -> list[str]:
    try:
        import yake
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        extractor = yake.KeywordExtractor(lan="en", n=2, top=top_n)
        kws = extractor.extract_keywords(text)
        return [kw for kw, _ in kws]
    except Exception:
        return []


def _keyword_focus(page: dict, primary_kw: str) -> dict[str, bool]:
    if not primary_kw:
        return {}
    kw = primary_kw.lower()
    title = page.get("title", "").lower()
    h1s = [h.lower() for h in page.get("h1", [])]
    url = page.get("url", "").lower()
    html = page.get("body_html", "").lower()
    first_para_match = bool(re.search(re.escape(kw), html[:2000]))
    return {
        "in_title": kw in title,
        "in_h1": any(kw in h for h in h1s),
        "in_url": kw.replace(" ", "-") in url or kw.replace(" ", "_") in url,
        "in_first_paragraph": first_para_match,
        "in_alt_text": kw in html,
    }


async def _autocomplete(seed: str, c: httpx.AsyncClient) -> list[str]:
    try:
        r = await c.get(
            "https://suggestqueries.google.com/complete/search",
            params={"q": seed, "client": "firefox"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            import json
            data = json.loads(r.text)
            return data[1][:8] if len(data) > 1 else []
    except Exception:
        pass
    return []


def _detect_cannibalization(page_keywords: list[dict]) -> list[dict]:
    kw_to_urls: dict[str, list[str]] = {}
    for pk in page_keywords:
        for kw in pk.get("top_keywords", [])[:5]:
            kw_to_urls.setdefault(kw, []).append(pk["url"])
    return [
        {"keyword": kw, "urls": urls}
        for kw, urls in kw_to_urls.items()
        if len(urls) > 1
    ]


# ── CSV mode (Semrush / Ahrefs / GSC exports) ─────────────────────────────

def parse_keyword_csv(content: bytes, source_hint: str = "") -> dict[str, Any]:
    """
    Parse a keyword CSV from Semrush, Ahrefs, or GSC.
    Maps columns to common schema: keyword, volume, position, url, difficulty, intent.
    """
    import csv
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
    rows = list(reader)
    if not rows:
        return {"rows": [], "columns_found": []}

    headers = list(rows[0].keys())
    col_map = _detect_columns(headers)
    mapped = []
    for row in rows:
        mapped.append({
            "keyword": row.get(col_map.get("keyword", ""), ""),
            "volume": _safe_int(row.get(col_map.get("volume", ""), "")),
            "position": _safe_int(row.get(col_map.get("position", ""), "")),
            "url": row.get(col_map.get("url", ""), ""),
            "difficulty": _safe_int(row.get(col_map.get("difficulty", ""), "")),
            "intent": _tag_intent(row.get(col_map.get("keyword", ""), "")),
        })
    return {"rows": mapped, "columns_found": list(col_map.keys()), "raw_headers": headers}


def _detect_columns(headers: list[str]) -> dict[str, str]:
    lower = {h.lower(): h for h in headers}
    mapping: dict[str, str] = {}
    for field, candidates in [
        ("keyword", ["keyword", "query", "key phrase", "term"]),
        ("volume", ["volume", "search volume", "avg. monthly searches", "searches"]),
        ("position", ["position", "pos.", "rank", "current position"]),
        ("url", ["url", "page", "landing page", "link"]),
        ("difficulty", ["kd", "keyword difficulty", "difficulty"]),
    ]:
        for c in candidates:
            if c in lower:
                mapping[field] = lower[c]
                break
    return mapping


def _safe_int(v: str) -> int | None:
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return None


def _tag_intent(keyword: str) -> str:
    kw = keyword.lower()
    if any(w in kw for w in ("buy", "price", "cost", "near me", "hire", "get", "order")):
        return "transactional"
    if any(w in kw for w in ("best", "vs", "review", "compare", "top")):
        return "commercial"
    if any(w in kw for w in ("how", "what", "why", "guide", "tutorial", "learn")):
        return "informational"
    return "navigational"
