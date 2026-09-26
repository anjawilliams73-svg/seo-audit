"""
Google Business Profile collector.
Public audit via Places API (free monthly credit).
Owner audit (Business Profile API) is a future phase.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx


async def collect(gbp_url: str | None, site_url: str, business_name: str | None) -> dict[str, Any]:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not key:
        return {
            "available": False,
            "note": "GOOGLE_PLACES_API_KEY not set. GBP audit skipped.",
        }

    if not gbp_url and not business_name:
        return {"available": False, "note": "No GBP link or business name provided."}

    # resolve place
    place = await _resolve_place(gbp_url, site_url, business_name, key)
    if not place:
        return {
            "available": False,
            "matched": False,
            "note": "No matching Google Business Profile found.",
        }

    return {
        "available": True,
        "matched": True,
        "place_id": place.get("place_id"),
        "name": place.get("name"),
        "address": place.get("formatted_address"),
        "phone": place.get("formatted_phone_number"),
        "website": place.get("website"),
        "primary_type": place.get("types", [None])[0],
        "types": place.get("types", []),
        "rating": place.get("rating"),
        "review_count": place.get("user_ratings_total"),
        "hours": place.get("opening_hours", {}).get("weekday_text"),
        "photos": len(place.get("photos", [])),
        "requires_confirmation": True,
        "nap": {
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "phone": place.get("formatted_phone_number"),
        },
    }


async def _resolve_place(
    gbp_url: str | None,
    site_url: str,
    business_name: str | None,
    key: str,
) -> dict | None:
    async with httpx.AsyncClient(timeout=10) as c:
        if gbp_url and "maps.google" in gbp_url or (gbp_url and "place" in gbp_url):
            place_id = _extract_place_id(gbp_url)
            if place_id:
                return await _details(place_id, key, c)

        # text search fallback
        domain = urlparse(site_url).netloc.lstrip("www.")
        query = business_name or domain
        r = await c.get(
            "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
            params={
                "input": query,
                "inputtype": "textquery",
                "fields": "place_id,name,formatted_address",
                "key": key,
            },
        )
        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        return await _details(candidates[0]["place_id"], key, c)


async def _details(place_id: str, key: str, c: httpx.AsyncClient) -> dict | None:
    fields = (
        "place_id,name,formatted_address,formatted_phone_number,"
        "website,types,rating,user_ratings_total,opening_hours,photos"
    )
    r = await c.get(
        "https://maps.googleapis.com/maps/api/place/details/json",
        params={"place_id": place_id, "fields": fields, "key": key},
    )
    result = r.json().get("result")
    return result


def _extract_place_id(url: str) -> str | None:
    m = re.search(r'place_id=([^&]+)', url)
    return m.group(1) if m else None
