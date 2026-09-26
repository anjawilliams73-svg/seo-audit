"""
Indexing checks: robots.txt, sitemaps, redirects, status codes, broken links.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


async def collect(start_url: str, pages: list[dict]) -> dict[str, Any]:
    base = _base(start_url)

    robots_text, sitemap_urls = await _fetch_robots_and_sitemap(base)
    redirects = _analyse_redirects(pages)
    broken = [p["url"] for p in pages if p["status"] == 404]
    status_breakdown = _status_breakdown(pages)
    www_redirect = await _check_www_redirect(base)
    indexing_directives = _parse_noindex(pages)
    sitemap_vs_crawl = _sitemap_coverage(sitemap_urls, [p["url"] for p in pages])

    return {
        "robots_found": bool(robots_text),
        "robots_text": robots_text,
        "sitemap_urls": sitemap_urls,
        "sitemap_count": len(sitemap_urls),
        "redirects_301": redirects["301"],
        "redirects_302": redirects["302"],
        "broken_links": broken,
        "broken_count": len(broken),
        "status_breakdown": status_breakdown,
        "www_redirect_ok": www_redirect,
        "noindex_pages": indexing_directives["noindex"],
        "nofollow_pages": indexing_directives["nofollow"],
        "sitemap_not_in_crawl": sitemap_vs_crawl["in_sitemap_not_crawled"],
        "crawled_not_in_sitemap": sitemap_vs_crawl["crawled_not_in_sitemap"],
    }


# ── helpers ───────────────────────────────────────────────────────────────

def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


async def _fetch_robots_and_sitemap(base: str) -> tuple[str, list[str]]:
    sitemap_urls: list[str] = []
    robots_text = ""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(f"{base}/robots.txt")
            if r.status_code == 200:
                robots_text = r.text
                # extract Sitemap directives
                for line in robots_text.splitlines():
                    if line.strip().lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        sitemap_urls.append(sm_url)

            if not sitemap_urls:
                # try default location
                r2 = await c.get(f"{base}/sitemap.xml")
                if r2.status_code == 200:
                    sitemap_urls.append(f"{base}/sitemap.xml")
                    sitemap_urls.extend(_extract_sitemap_index(r2.text, base))
    except Exception:
        pass
    return robots_text, sitemap_urls


def _extract_sitemap_index(xml: str, base: str) -> list[str]:
    # sitemap index entries
    return re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", xml)


def _analyse_redirects(pages: list[dict]) -> dict[str, list[str]]:
    r301, r302 = [], []
    for p in pages:
        chain = p.get("redirect_chain", [])
        if chain:
            # determine type from status
            s = p.get("status", 0)
            if s == 301 or (chain and len(chain) > 1):
                r301.append(p["url"])
            elif s == 302:
                r302.append(p["url"])
    return {"301": r301, "302": r302}


def _status_breakdown(pages: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for p in pages:
        s = p.get("status", 0)
        counts[s] = counts.get(s, 0) + 1
    return counts


async def _check_www_redirect(base: str) -> bool:
    parsed = urlparse(base)
    if parsed.netloc.startswith("www."):
        non_www = base.replace("www.", "", 1)
        test = non_www
    else:
        test = base.replace("://", "://www.", 1)
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
            r = await c.get(test)
            return r.status_code in (301, 302)
    except Exception:
        return False


def _parse_noindex(pages: list[dict]) -> dict[str, list[str]]:
    noindex, nofollow = [], []
    for p in pages:
        html = p.get("body_html", "")
        if re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', html, re.I):
            noindex.append(p["url"])
        if re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*nofollow', html, re.I):
            nofollow.append(p["url"])
    return {"noindex": noindex, "nofollow": nofollow}


def _sitemap_coverage(sitemap_urls: list[str], crawled: list[str]) -> dict[str, list[str]]:
    crawled_set = set(crawled)
    sitemap_set = set(sitemap_urls)
    return {
        "in_sitemap_not_crawled": list(sitemap_set - crawled_set),
        "crawled_not_in_sitemap": list(crawled_set - sitemap_set),
    }
