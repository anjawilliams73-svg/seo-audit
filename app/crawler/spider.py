"""
Crawl a site with advertools. Returns a list of page dicts with fields the
collectors need. Max pages is read from config/settings.yaml.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import advertools as adv
import httpx
import pandas as pd
import yaml

_CFG_PATH = Path(__file__).parents[2] / "config" / "settings.yaml"
with _CFG_PATH.open() as _f:
    _CFG = yaml.safe_load(_f)

MAX_PAGES: int = _CFG["crawl"]["max_pages"]
CONCURRENCY: int = _CFG["crawl"]["concurrency"]
USER_AGENT: str = _CFG["crawl"]["user_agent"]
RESPECT_ROBOTS: bool = _CFG["crawl"]["respect_robots"]


def _host(url: str) -> str:
    return urlparse(url).netloc


def crawl(start_url: str) -> list[dict[str, Any]]:
    """
    Crawl start_url up to MAX_PAGES. Return a list of page records.
    Each record contains the fields downstream collectors expect.
    """
    with tempfile.NamedTemporaryFile(suffix=".jl", delete=False) as tmp:
        output_file = tmp.name

    adv.crawl(
        url_list=[start_url],
        output_file=output_file,
        follow_links=True,
        custom_settings={
            "USER_AGENT": USER_AGENT,
            "CLOSESPIDER_PAGECOUNT": MAX_PAGES,
            "CONCURRENT_REQUESTS": CONCURRENCY,
            "ROBOTSTXT_OBEY": RESPECT_ROBOTS,
            "DOWNLOAD_TIMEOUT": 15,
            "LOG_LEVEL": "WARNING",
        },
    )

    df = pd.read_json(output_file, lines=True)
    Path(output_file).unlink(missing_ok=True)

    if df.empty:
        return []

    base_host = _host(start_url)
    pages: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        url = str(row.get("url", ""))
        if not url or _host(url) != base_host:
            continue

        status = int(row.get("status", 0) or 0)
        content_type = str(row.get("content_type", "") or "")
        if "text/html" not in content_type:
            continue

        body = str(row.get("body", "") or "")

        pages.append({
            "url": url,
            "status": status,
            "title": _extract_title(body),
            "meta_description": _extract_meta(body, "description"),
            "h1": _extract_tags(body, "h1"),
            "h2": _extract_tags(body, "h2"),
            "h3": _extract_tags(body, "h3"),
            "canonical": _extract_canonical(body),
            "body_html": body,
            "word_count": _word_count(body),
            "internal_links": _count_links(body, base_host, internal=True),
            "external_links": _count_links(body, base_host, internal=False),
            "images": _extract_images(body),
            "nofollow_links": _count_nofollow(body),
            "redirect_chain": _get_redirect_chain(url, row),
        })

    return pages


# ── helpers ───────────────────────────────────────────────────────────────

def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]*)</title>", html, re.I)
    return (m.group(1) or "").strip() if m else ""


def _extract_meta(html: str, name: str) -> str:
    pat = (
        rf'<meta[^>]+name=["\']{name}["\'][^>]+content=["\']([^"\']*)["\']'
        rf'|<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']{name}["\']'
    )
    m = re.search(pat, html, re.I)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip()


def _extract_tags(html: str, tag: str) -> list[str]:
    return [
        re.sub(r"<[^>]+>", "", t).strip()
        for t in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.I | re.S)
    ]


def _extract_canonical(html: str) -> str | None:
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.I)
    return m.group(1).strip() if m else None


def _word_count(html: str) -> int:
    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return len([w for w in stripped.split() if len(w) > 1])


def _count_links(html: str, base_host: str, *, internal: bool) -> int:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    count = 0
    for h in hrefs:
        if h.startswith("#") or h.startswith("mailto:") or h.startswith("tel:"):
            if internal:
                count += 1
            continue
        if h.startswith("/") or base_host in h:
            if internal:
                count += 1
        elif h.startswith("http"):
            if not internal:
                count += 1
    return count


def _count_nofollow(html: str) -> int:
    return len(re.findall(r'rel=["\'][^"\']*nofollow[^"\']*["\']', html, re.I))


def _extract_images(html: str) -> list[dict[str, str]]:
    imgs = []
    for m in re.finditer(r"<img([^>]+)>", html, re.I):
        attrs = m.group(1)
        src_m = re.search(r'src=["\']([^"\']+)["\']', attrs, re.I)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', attrs, re.I)
        imgs.append({
            "src": src_m.group(1) if src_m else "",
            "alt": alt_m.group(1) if alt_m else None,
        })
    return imgs


def _get_redirect_chain(url: str, row: Any) -> list[str]:
    redirects = getattr(row, "redirect_urls", None)
    if redirects and isinstance(redirects, list):
        return redirects
    return []
