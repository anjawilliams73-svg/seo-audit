"""
FastAPI app for the SEO Audit Tool.
Endpoints:
  POST /audit         — start audit, returns job_id + candidate competitors
  GET  /audit/{id}    — poll status
  GET  /report/{id}   — download HTML report
  GET  /report/{id}/pdf — download PDF report
  POST /audit/{id}/confirm-competitors — confirm competitor set, triggers comparison
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.routers import keywords as keywords_router

load_dotenv()

app = FastAPI(title="SEO Audit Tool", version="1.0.0")

_origin_env = os.getenv("ALLOWED_ORIGIN", "*")
ALLOWED_ORIGINS = ["*"] if _origin_env == "*" else [o.strip() for o in _origin_env.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(keywords_router.router)

# In-memory job store (use Redis in production)
_JOBS: dict[str, dict[str, Any]] = {}
_REPORT_DIR = Path("/tmp/seo_reports")
_REPORT_DIR.mkdir(exist_ok=True)


# ── POST /audit ──────────────────────────────────────────────────────────────

@app.post("/audit")
async def start_audit(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    gbp_url: str | None = Form(None),
    keyword_csv: UploadFile | None = File(None),
):
    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    job_id = str(uuid.uuid4())[:8]
    _JOBS[job_id] = {"status": "queued", "url": clean_url}

    kw_content: bytes | None = None
    if keyword_csv:
        kw_content = await keyword_csv.read()

    background_tasks.add_task(_run_pipeline, job_id, clean_url, gbp_url, kw_content)
    return {"job_id": job_id, "status": "queued"}


async def _run_pipeline(
    job_id: str,
    url: str,
    gbp_url: str | None,
    kw_content: bytes | None,
) -> None:
    from app.pipeline import run
    _JOBS[job_id]["status"] = "running"
    try:
        result = await run(
            job_id=job_id,
            url=url,
            gbp_url=gbp_url,
            keyword_csv_content=kw_content,
            output_dir=_REPORT_DIR / job_id,
        )
        _JOBS[job_id].update(result)
        _JOBS[job_id]["status"] = "complete"
    except Exception as exc:
        _JOBS[job_id]["status"] = "error"
        _JOBS[job_id]["error"] = str(exc)


# ── GET /audit/{id} ──────────────────────────────────────────────────────────

@app.get("/audit/{job_id}")
async def get_audit(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    # return summary (not the full pages list — too large)
    return {
        "job_id": job_id,
        "status": job["status"],
        "url": job.get("url"),
        "scores": job.get("scores"),
        "pages_crawled": job.get("pages_crawled"),
        "error": job.get("error"),
    }


# ── GET /report/{id} ─────────────────────────────────────────────────────────

@app.get("/report/{job_id}")
async def get_html_report(job_id: str):
    job = _JOBS.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(status_code=404, detail="Report not ready.")
    html_path = Path(job.get("html_path", ""))
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Report file missing.")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/report/{job_id}/pdf")
async def get_pdf_report(job_id: str):
    job = _JOBS.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(status_code=404, detail="Report not ready.")
    pdf_path = Path(job.get("pdf_path", ""))
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing.")
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"seo-audit-{job_id}.pdf",
    )


# ── POST /audit/{id}/confirm-competitors ─────────────────────────────────────

@app.post("/audit/{job_id}/confirm-competitors")
async def confirm_competitors(
    job_id: str,
    background_tasks: BackgroundTasks,
    competitor_urls: list[str],
):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    _JOBS[job_id]["confirmed_competitors"] = competitor_urls
    background_tasks.add_task(_run_competitor_comparison, job_id, competitor_urls)
    return {"job_id": job_id, "status": "running_comparison"}


async def _run_competitor_comparison(job_id: str, confirmed: list[str]) -> None:
    from app.collectors.competitors import compare
    job = _JOBS[job_id]
    try:
        result = await compare(confirmed, job["url"], job.get("pages", []))
        _JOBS[job_id]["competitor_comparison"] = result
    except Exception as exc:
        _JOBS[job_id]["competitor_error"] = str(exc)


# ── health ───────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {"status": "ok", "service": "SEO Audit Tool"}
