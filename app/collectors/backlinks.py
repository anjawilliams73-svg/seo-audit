"""
Common Crawl backlink estimate.
This is partial and best-effort only. Results are labelled as estimates.
Free tier — no API key needed, but rate-limited.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

# Try multiple recent CC indexes in order; stop at first successful response
_CC_INDEXES = [
    "https://index.commoncrawl.org/CC-MAIN-2025-13-index",
    "https://index.commoncrawl.org/CC-MAIN-2024-51-index",
    "https://index.commoncrawl.org/CC-MAIN-2024-42-index",
]


async def collect(start_url: str) -> dict[str, Any]:
    import json as _json
    host = urlparse(start_url).netloc.lstrip("www.")
    # Query pages crawled ON this domain (coverage signal, not true backlinks)
    params = {
        "url": f"*.{host}",
        "output": "json",
        "fl": "url,timestamp,status",
        "limit": "1000",
        "filter": "status:200",
    }
    last_exc = ""
    async with httpx.AsyncClient(timeout=25) as c:
        for api_url in _CC_INDEXES:
            try:
                r = await c.get(api_url, params=params)
                if r.status_code != 200:
                    last_exc = f"HTTP {r.status_code} from {api_url}"
                    continue

                lines = [ln.strip() for ln in r.text.strip().splitlines() if ln.strip()]
                records = []
                for ln in lines:
                    try:
                        records.append(_json.loads(ln))
                    except Exception:
                        pass

                if not records:
                    last_exc = "empty response"
                    continue

                unique_urls = {rec["url"] for rec in records}
                unique_paths = len(unique_urls)

                return {
                    "available": True,
                    "is_estimate": True,
                    "source": "Common Crawl",
                    "linking_domains": None,   # CC index doesn't expose inbound links
                    "inbound_urls": None,
                    "pages_indexed": unique_paths,
                    "note": (
                        f"Common Crawl found {unique_paths} pages from this site in its index. "
                        "This reflects crawl coverage, not inbound backlinks. "
                        "For true backlink data use Ahrefs, Moz, or Semrush."
                    ),
                }
            except Exception as exc:
                last_exc = str(exc)
                continue

    return _unavailable(last_exc)


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "is_estimate": True,
        "source": "Common Crawl",
        "linking_domains": None,
        "inbound_urls": None,
        "note": "Backlink data not available. Common Crawl could not be reached.",
    }
