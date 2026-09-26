"""
Keyword Research — Google Autocomplete-based suggestions, free, no API key.
POST /keywords  { keyword, location? }  → { keywords: [...] }
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter()

_AUTOCOMPLETE = "https://suggestqueries.google.com/complete/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; keyword-research/1.0)"}

_QUESTION_PREFIXES = [
    "who", "what", "when", "where", "why", "how", "is", "are", "can",
    "does", "do", "will", "should", "which",
]
_MODIFIERS = [
    "best", "top", "cheap", "affordable", "near me", "cost", "price",
    "vs", "alternative", "review", "hire", "service",
]
_ALPHABET = list("abcdefghijklmnopqrstuvwxyz")


async def _fetch(client: httpx.AsyncClient, query: str) -> list[str]:
    try:
        r = await client.get(
            _AUTOCOMPLETE,
            params={"client": "firefox", "q": query, "hl": "en"},
            headers=_HEADERS,
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                return [s.lower().strip() for s in data[1] if s]
    except Exception:
        pass
    return []


def _classify_intent(kw: str) -> str:
    kw_l = kw.lower()
    if any(kw_l.startswith(q + " ") for q in _QUESTION_PREFIXES):
        return "question"
    if any(w in kw_l for w in ["near me", "near by", " in ", "local"]):
        return "local"
    if any(w in kw_l for w in ["buy", "hire", "cost", "price", "cheap", "affordable", "best", "top"]):
        return "commercial"
    return "informational"


@router.post("/keywords")
async def keyword_research(body: dict[str, Any]) -> dict[str, Any]:
    seed = (body.get("keyword") or "").strip().lower()
    location = (body.get("location") or "").strip()
    if not seed:
        return {"keywords": [], "error": "keyword is required"}

    queries: list[str] = [seed]

    # A–Z expansion
    for letter in _ALPHABET:
        queries.append(f"{seed} {letter}")

    # Question prefixes
    for prefix in _QUESTION_PREFIXES:
        queries.append(f"{prefix} {seed}")

    # Modifiers
    for mod in _MODIFIERS:
        queries.append(f"{seed} {mod}")

    # Location variants
    if location:
        queries += [
            f"{seed} in {location}",
            f"{seed} near {location}",
            f"best {seed} in {location}",
        ]
    else:
        queries += [f"{seed} near me", f"best {seed} near me"]

    # Fetch all in parallel (batch to avoid rate limits)
    seen: set[str] = set()
    results: list[dict] = []

    async with httpx.AsyncClient() as client:
        batch_size = 10
        for i in range(0, len(queries), batch_size):
            batch = queries[i : i + batch_size]
            suggestions_list = await asyncio.gather(
                *[_fetch(client, q) for q in batch]
            )
            for suggestions in suggestions_list:
                for kw in suggestions:
                    clean = re.sub(r"\s+", " ", kw).strip()
                    if clean and clean not in seen and seed in clean:
                        seen.add(clean)
                        results.append({
                            "keyword": clean,
                            "intent": _classify_intent(clean),
                        })
            # small pause between batches to be polite
            if i + batch_size < len(queries):
                await asyncio.sleep(0.3)

    # Sort: local first, then commercial, question, informational; alphabetical within
    _order = {"local": 0, "commercial": 1, "question": 2, "informational": 3}
    results.sort(key=lambda x: (_order.get(x["intent"], 9), x["keyword"]))

    return {"keywords": results, "count": len(results), "seed": seed}
