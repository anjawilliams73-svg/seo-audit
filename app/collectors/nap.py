"""
NAP consistency — compares Name/Address/Phone across:
  1. Website (footer + contact page + JSON-LD)
  2. GBP profile (from gbp collector)
  3. LocalBusiness / Organization JSON-LD on site

Scores per SCORING.md: identical=10, minor formatting=7, phone/suite differs=4,
address/name differs=2, NAP missing from website=0.
"""
from __future__ import annotations

import re
from typing import Any


def collect(pages: list[dict], gbp_data: dict, schema_data: dict) -> dict[str, Any]:
    site_nap = _extract_site_nap(pages)
    gbp_nap = gbp_data.get("nap") if gbp_data.get("available") else None
    schema_nap = _extract_schema_nap(pages)

    if not site_nap["name"] and not site_nap["phone"] and not site_nap["address"]:
        return {
            "score": 0,
            "site": site_nap,
            "gbp": gbp_nap,
            "schema": schema_nap,
            "mismatches": [],
            "note": "NAP not found on website.",
        }

    mismatches = _compare(site_nap, gbp_nap, schema_nap)
    score = _score(site_nap, mismatches)

    return {
        "score": score,
        "site": site_nap,
        "gbp": gbp_nap,
        "schema": schema_nap,
        "mismatches": mismatches,
    }


def _extract_site_nap(pages: list[dict]) -> dict[str, str | None]:
    # look in footer and contact pages first, then fall back to any page
    priority = [p for p in pages if "contact" in p["url"].lower() or "footer" in p.get("body_html", "").lower()[:500]]
    all_pages = priority + [p for p in pages if p not in priority]

    for page in all_pages:
        html = page.get("body_html", "")
        phone = _find_phone(html)
        address = _find_address(html)
        name = _find_org_name_from_schema(html)
        if phone or address:
            return {"name": name, "address": address, "phone": phone}

    return {"name": None, "address": None, "phone": None}


def _extract_schema_nap(pages: list[dict]) -> dict[str, str | None]:
    for page in pages:
        html = page.get("body_html", "")
        import json, re as _re
        for m in _re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html, _re.I):
            try:
                obj = json.loads(m.group(1))
                t = obj.get("@type", "")
                if t in ("LocalBusiness", "Organization"):
                    return {
                        "name": obj.get("name"),
                        "address": _flatten_address(obj.get("address")),
                        "phone": obj.get("telephone"),
                    }
            except Exception:
                continue
    return {"name": None, "address": None, "phone": None}


def _flatten_address(addr: Any) -> str | None:
    if not addr:
        return None
    if isinstance(addr, str):
        return addr
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress"),
            addr.get("addressLocality"),
            addr.get("addressRegion"),
            addr.get("postalCode"),
            addr.get("addressCountry"),
        ]
        return ", ".join(p for p in parts if p)
    return None


def _find_phone(html: str) -> str | None:
    m = re.search(r'(?:tel:|href=["\']tel:)([+\d\s\-().]{7,20})', html, re.I)
    if m:
        return m.group(1).strip()
    m2 = re.search(r'\b(\+?[\d\s\-().]{10,20})\b', html)
    return m2.group(1).strip() if m2 else None


def _find_address(html: str) -> str | None:
    # look for address-like text in schema or common patterns
    m = re.search(
        r'<address[^>]*>([\s\S]*?)</address>',
        html, re.I,
    )
    if m:
        return re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
    return None


def _find_org_name_from_schema(html: str) -> str | None:
    import json
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html, re.I,
    ):
        try:
            obj = json.loads(m.group(1))
            if obj.get("@type") in ("LocalBusiness", "Organization"):
                return obj.get("name")
        except Exception:
            continue
    return None


def _compare(
    site: dict,
    gbp: dict | None,
    schema: dict | None,
) -> list[dict]:
    mismatches = []
    sources = {"site": site, "gbp": gbp, "schema": schema}
    for field in ("name", "address", "phone"):
        values = {k: (v.get(field) if v else None) for k, v in sources.items()}
        non_null = [v for v in values.values() if v]
        if len(set(_normalise(v) for v in non_null)) > 1:
            mismatches.append({
                "field": field,
                "site": values["site"],
                "gbp": values["gbp"],
                "schema": values["schema"],
            })
    return mismatches


def _normalise(v: str) -> str:
    return re.sub(r'\s+', ' ', v.lower().strip())


def _score(site_nap: dict, mismatches: list) -> int:
    if not any(site_nap.values()):
        return 0
    if not mismatches:
        return 10
    fields = {m["field"] for m in mismatches}
    if fields <= {"phone"}:
        return 4
    if fields & {"address", "name"}:
        return 2
    return 7  # minor formatting only
