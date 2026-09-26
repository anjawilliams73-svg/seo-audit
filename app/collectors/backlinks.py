"""
Common Crawl backlink estimate.
This is partial and best-effort only. Results are labelled as estimates.
Free tier — no API key needed, but rate-limited.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

_CC_API = "https://index.commoncrawl.org/CC-MAIN-2024-42-index"


async def collect(start_url: str) -> dict[str, Any]:
    host = urlparse(start_url).netloc.lstrip("www.")
    params = {
        "url": f"*.{host}",
        "output": "json",
        "fl": "url,timestamp,status",
        "limit": "500",
        "filter": "status:200",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(_CC_API, params=params)
            if r.status_code != 200:
                return _unavailable("non-200 from Common Crawl")

            lines = [l.strip() for l in r.text.strip().splitlines() if l.strip()]
            import json
            records = []
            for line in lines:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

            unique_urls = {rec["url"] for rec in records}
            unique_domains: set[str] = set()
            for rec in records:
                try:
                    unique_domains.add(urlparse(rec["url"]).netloc)
                except Exception:
                    pass

            return {
                "available": True,
                "is_estimate": True,
                "source": "Common Crawl",
                "linking_domains": len(unique_domains) - 1,  # exclude self
                "inbound_urls": len(unique_urls),
                "note": "Partial estimate from Common Crawl index. Not a complete backlink count.",
            }
    except Exception as exc:
        return _unavailable(str(exc))


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
