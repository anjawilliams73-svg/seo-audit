"""
Screenshots via Playwright — homepage desktop + mobile.
Saves to a temp directory and returns file paths.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any


async def collect(url: str) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"available": False, "note": "Playwright not installed."}

    results: dict[str, Any] = {"available": True, "screenshots": []}
    out_dir = Path(tempfile.mkdtemp(prefix="seo_screenshots_"))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # desktop
        page_d = await browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            await page_d.goto(url, wait_until="networkidle", timeout=30000)
            desktop_path = out_dir / "desktop.png"
            await page_d.screenshot(path=str(desktop_path), full_page=False)
            results["screenshots"].append({"type": "desktop", "path": str(desktop_path)})
        except Exception as exc:
            results["screenshots"].append({"type": "desktop", "error": str(exc)})
        finally:
            await page_d.close()

        # mobile
        page_m = await browser.new_page(viewport={"width": 390, "height": 844})
        try:
            await page_m.goto(url, wait_until="networkidle", timeout=30000)
            mobile_path = out_dir / "mobile.png"
            await page_m.screenshot(path=str(mobile_path), full_page=False)
            results["screenshots"].append({"type": "mobile", "path": str(mobile_path)})
        except Exception as exc:
            results["screenshots"].append({"type": "mobile", "error": str(exc)})
        finally:
            await page_m.close()

        await browser.close()

    return results
