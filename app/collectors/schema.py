"""Schema / structured data collector using extruct."""
from __future__ import annotations

import re
from typing import Any

import extruct


_WANTED_TYPES = {
    "Organization", "LocalBusiness", "Person", "WebSite", "WebPage",
    "Article", "BlogPosting", "Product", "Service", "FAQPage", "HowTo",
    "BreadcrumbList", "Event", "Review", "ItemList",
}


def collect(pages: list[dict]) -> dict[str, Any]:
    sitewide_types: set[str] = set()
    page_results: list[dict] = []

    for p in pages:
        html = p.get("body_html", "")
        url = p["url"]
        types = _extract_types(html)
        sitewide_types.update(types)
        page_results.append({
            "url": url,
            "schema_types": list(types),
            "has_json_ld": bool(re.search(r'<script[^>]+type=["\']application/ld\+json["\']', html, re.I)),
            "has_faq_or_howto": any(t in ("FAQPage", "HowTo") for t in types),
            "has_breadcrumb": "BreadcrumbList" in types,
            "has_organization_or_person": any(t in ("Organization", "LocalBusiness", "Person") for t in types),
        })

    missing_types = list(_WANTED_TYPES - sitewide_types)
    pages_with_no_schema = [r["url"] for r in page_results if not r["schema_types"]]

    return {
        "sitewide_types": list(sitewide_types),
        "missing_types": missing_types,
        "pages_missing_schema": pages_with_no_schema,
        "page_schema": page_results,
        "has_organization_sitewide": any(
            t in ("Organization", "LocalBusiness") for t in sitewide_types
        ),
    }


def _extract_types(html: str) -> set[str]:
    types: set[str] = set()
    try:
        data = extruct.extract(html, syntaxes=["json-ld", "microdata", "opengraph"])
        for item in data.get("json-ld", []):
            _walk(item, types)
        for item in data.get("microdata", []):
            t = item.get("type", "")
            if t:
                types.add(t.split("/")[-1].split("#")[-1])
    except Exception:
        pass
    return types


def _walk(obj: Any, types: set[str]) -> None:
    if isinstance(obj, dict):
        t = obj.get("@type")
        if t:
            for v in (t if isinstance(t, list) else [t]):
                types.add(str(v).split("/")[-1].split("#")[-1])
        for v in obj.values():
            _walk(v, types)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, types)
