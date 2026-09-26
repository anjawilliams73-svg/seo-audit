"""
Screenshots via Playwright — homepage desktop + mobile.
Saves to a temp directory and returns file paths.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any


async def _capture(browser, url: str, viewport: dict, out_path: Path, label: str) -> dict:
    page = await browser.new_page(viewport=viewport)
    try:
        # domcontentloaded is more reliable than networkidle on pages with persistent connections
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Give scripts 2s to render visible content
        await asyncio.sleep(2)
        await page.screenshot(path=str(out_path), full_page=False)
        return {"type": label, "path": str(out_path)}
    except Exception as exc:
        return {"type": label, "error": str(exc)}
    finally:
        await page.close()


async def collect(url: str) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"available": False, "note": "Playwright not installed."}

    results: dict[str, Any] = {"available": True, "screenshots": []}
    out_dir = Path(tempfile.mkdtemp(prefix="seo_screenshots_"))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        desktop = await _capture(
            browser, url,
            viewport={"width": 1280, "height": 800},
            out_path=out_dir / "desktop.png",
            label="desktop",
        )
        results["screenshots"].append(desktop)

        mobile = await _capture(
            browser, url,
            viewport={"width": 390, "height": 844},
            out_path=out_dir / "mobile.png",
            label="mobile",
        )
        results["screenshots"].append(mobile)

        await browser.close()

    return results
