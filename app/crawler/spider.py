"""
Async httpx crawler — no Scrapy dependency.
Crawls up to MAX_PAGES pages of start_url, staying on the same host.
Returns a list of page dicts that downstream collectors expect.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

_CFG_PATH = Path(__file__).parents[2] / "config" / "settings.yaml"
with _CFG_PATH.open() as _f:
    _CFG = yaml.safe_load(_f)

MAX_PAGES: int = _CFG["crawl"]["max_pages"]
CONCURRENCY: int = min(_CFG["crawl"]["concurrency"], 8)
USER_AGENT: str = _CFG["crawl"]["user_agent"]

_HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}


def _host(url: str) -> str:
    return urlparse(url).netloc


def crawl(start_url: str) -> list[dict[str, Any]]:
    return asyncio.run(_crawl_async(start_url))


async def _crawl_async(start_url: str) -> list[dict[str, Any]]:
    base_host = _host(start_url)
    visited: set[str] = set()
    queue: list[str] = [start_url]
    pages: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(
        headers=_HEADERS,
        follow_redirects=True,
        timeout=15,
        limits=httpx.Limits(max_connections=CONCURRENCY),
    ) as client:
        while queue and len(pages) < MAX_PAGES:
            batch = []
            while queue and len(batch) < CONCURRENCY:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                batch.append(url)

            results = await asyncio.gather(
                *[_fetch(client, sem, url, base_host) for url in batch],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, dict) and result:
                    pages.append(result)
                    # enqueue new links
                    for link in result.pop("_links", []):
                        if link not in visited and len(visited) < MAX_PAGES * 2:
                            queue.append(link)
                if len(pages) >= MAX_PAGES:
                    break

    return pages[:MAX_PAGES]


async def _fetch(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
    base_host: str,
) -> dict[str, Any] | None:
    async with sem:
        try:
            resp = await client.get(url)
            ct = resp.headers.get("content-type", "")
            if "text/html" not in ct:
                return None
            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            links = _extract_links(soup, url, base_host)

            return {
                "url": str(resp.url),
                "status": resp.status_code,
                "title": _text(soup.find("title")),
                "meta_description": _meta(soup, "description"),
                "h1": [t.get_text(strip=True) for t in soup.find_all("h1")],
                "h2": [t.get_text(strip=True) for t in soup.find_all("h2")],
                "h3": [t.get_text(strip=True) for t in soup.find_all("h3")],
                "canonical": _canonical(soup),
                "body_html": html,
                "word_count": _word_count(soup),
                "internal_links": sum(1 for l in links if _host(l) == base_host),
                "external_links": sum(1 for l in links if _host(l) != base_host),
                "images": _images(soup),
                "nofollow_links": _nofollow(soup),
                "redirect_chain": [str(r.url) for r in resp.history],
                "_links": [l for l in links if _host(l) == base_host],
            }
        except Exception:
            return None


def _text(tag: Any) -> str:
    return tag.get_text(strip=True) if tag else ""


def _meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.I)})
    return (tag.get("content") or "").strip() if tag else ""


def _canonical(soup: BeautifulSoup) -> str | None:
    tag = soup.find("link", rel="canonical")
    return tag.get("href") if tag else None


def _word_count(soup: BeautifulSoup) -> int:
    for t in soup(["script", "style"]):
        t.decompose()
    return len(soup.get_text().split())


def _extract_links(soup: BeautifulSoup, base_url: str, base_host: str) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(base_url, href).split("#")[0].split("?")[0]
        if full.startswith("http"):
            links.append(full)
    return links


def _images(soup: BeautifulSoup) -> list[dict[str, str]]:
    return [
        {"src": img.get("src", ""), "alt": img.get("alt")}
        for img in soup.find_all("img")
    ]


def _nofollow(soup: BeautifulSoup) -> int:
    return sum(
        1 for a in soup.find_all("a", rel=True)
        if "nofollow" in (a.get("rel") or [])
    )
