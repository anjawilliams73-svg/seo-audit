"""
Social profile detection from crawled HTML.
YouTube activity via YouTube Data API v3 if key available.
Other platforms: link found only, activity not checked.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

_ACTIVE_DAYS = 90

_PLATFORMS = [
    ("Facebook",  r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+'),
    ("Instagram", r'https?://(?:www\.)?instagram\.com/[^\s"\'<>]+'),
    ("LinkedIn",  r'https?://(?:www\.)?linkedin\.com/(?:in|company)/[^\s"\'<>]+'),
    ("Twitter/X", r'https?://(?:www\.)?(?:twitter|x)\.com/[^\s"\'<>]+'),
    ("YouTube",   r'https?://(?:www\.)?youtube\.com/(?:channel|c|user|@)[^\s"\'<>]+'),
    ("TikTok",    r'https?://(?:www\.)?tiktok\.com/@[^\s"\'<>]+'),
    ("Pinterest", r'https?://(?:www\.)?pinterest\.com/[^\s"\'<>]+'),
]


async def collect(pages: list[dict]) -> dict[str, Any]:
    # collect all hrefs from all pages
    all_html = "\n".join(p.get("body_html", "") for p in pages)
    found: dict[str, str] = {}
    for name, pattern in _PLATFORMS:
        m = re.search(pattern, all_html, re.I)
        if m:
            found[name] = m.group(0).rstrip(".,;)")

    profiles = []
    for name, url in found.items():
        info: dict[str, Any] = {"platform": name, "url": url, "status": "unknown"}
        if name == "YouTube":
            info.update(await _youtube_activity(url))
        else:
            info["status"] = "link_found"
            info["note"] = "Activity not checked (no free API)."
        profiles.append(info)

    # platforms with no link found
    found_names = {p["platform"] for p in profiles}
    for name, _ in _PLATFORMS:
        if name not in found_names:
            profiles.append({"platform": name, "url": None, "status": "not_found"})

    return {"profiles": profiles, "found_count": len(found)}


async def _youtube_activity(channel_url: str) -> dict[str, Any]:
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        return {"status": "link_found", "note": "YouTube API key not set — activity not checked."}

    handle = _extract_handle(channel_url)
    if not handle:
        return {"status": "link_found", "note": "Could not parse channel handle."}

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # resolve handle to channel id
            r = await c.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet,statistics", "forHandle": handle, "key": key},
            )
            data = r.json()
            items = data.get("items", [])
            if not items:
                return {"status": "link_found", "note": "Channel not found via API."}
            item = items[0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            # get last upload date
            published = snippet.get("publishedAt", "")
            last_upload = await _last_upload(item["id"], key, c)

            status = "unknown"
            if last_upload:
                delta = (datetime.now(timezone.utc) - last_upload).days
                status = "active" if delta <= _ACTIVE_DAYS else "inactive"

            return {
                "status": status,
                "subscribers": stats.get("subscriberCount"),
                "video_count": stats.get("videoCount"),
                "last_upload": last_upload.isoformat() if last_upload else None,
                "days_since_upload": delta if last_upload else None,
            }
    except Exception as exc:
        return {"status": "link_found", "note": f"YouTube API error: {exc}"}


async def _last_upload(channel_id: str, key: str, c: httpx.AsyncClient) -> datetime | None:
    try:
        r = await c.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "order": "date",
                "maxResults": "1",
                "type": "video",
                "key": key,
            },
        )
        items = r.json().get("items", [])
        if items:
            pub = items[0]["snippet"]["publishedAt"]
            return datetime.fromisoformat(pub.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def _extract_handle(url: str) -> str:
    m = re.search(r'youtube\.com/(?:channel/|c/|user/|@)([^/?&\s]+)', url, re.I)
    return m.group(1) if m else ""
