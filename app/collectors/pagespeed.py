"""PageSpeed Insights collector — mobile strategy, up to 6 pages."""
from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote_plus

import httpx

_PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_PAGES_TO_TEST = 6
log = logging.getLogger(__name__)


async def collect(urls: list[str]) -> dict[str, Any]:
    key = (os.getenv("PAGESPEED_API_KEY") or "").strip()
    if key:
        log.info("PSI: using API key (len=%d)", len(key))
    else:
        log.warning("PSI: no API key — keyless quota applies")
    results: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=45) as client:
        for url in urls[:_PAGES_TO_TEST]:
            qs = f"url={quote_plus(url)}&strategy=mobile"
            for cat in ("performance", "seo", "accessibility", "best-practices"):
                qs += f"&category={cat}"
            if key:
                qs += f"&key={key}"
            try:
                r = await client.get(f"{_PSI}?{qs}")
                log.info("PSI %s → HTTP %d", url, r.status_code)
                if r.status_code == 200:
                    parsed = _parse(r.json())
                    # Detect empty response (quota hit returns 200 with no lighthouse data)
                    if parsed.get("performance") is None and parsed.get("lcp", {}).get("value") is None:
                        err_body = r.json().get("error", {})
                        results[url] = {"error": f"empty_response: {err_body.get('message','no lighthouse data')}"}
                    else:
                        results[url] = parsed
                elif r.status_code == 429:
                    results[url] = {"error": "rate_limited"}
                else:
                    results[url] = {"error": f"http_{r.status_code}"}
            except Exception as exc:
                results[url] = {"error": str(exc)}

    return results


def _parse(data: dict) -> dict[str, Any]:
    lhr = data.get("lighthouseResult", {})
    audits = lhr.get("audits", {})
    cats = lhr.get("categories", {})

    def cat_score(k: str) -> int | None:
        c = cats.get(k)
        return round((c["score"] or 0) * 100) if c else None

    def val(k: str) -> str:
        return audits.get(k, {}).get("displayValue", "—")

    def sc(k: str) -> float | None:
        return audits.get(k, {}).get("score")

    opportunities = sorted(
        [
            {
                "title": a["title"],
                "displayValue": a.get("displayValue", ""),
                "score": a.get("score", 1),
            }
            for a in audits.values()
            if a.get("details", {}).get("type") == "opportunity"
            and a.get("score") is not None
            and a["score"] < 0.9
        ],
        key=lambda x: x["score"],
    )[:5]

    return {
        "performance": cat_score("performance"),
        "seo": cat_score("seo"),
        "accessibility": cat_score("accessibility"),
        "best_practices": cat_score("best-practices"),
        "lcp": {"value": val("largest-contentful-paint"), "score": sc("largest-contentful-paint")},
        "tbt": {"value": val("total-blocking-time"), "score": sc("total-blocking-time")},
        "cls": {"value": val("cumulative-layout-shift"), "score": sc("cumulative-layout-shift")},
        "fcp": {"value": val("first-contentful-paint"), "score": sc("first-contentful-paint")},
        "opportunities": opportunities,
    }
