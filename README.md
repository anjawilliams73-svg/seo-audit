# SEO Audit Tool — Python Backend

Free, fully automated SEO audit. User enters a URL → crawl → score → PDF + HTML report.

## Stack
- Python 3.11 / FastAPI
- advertools (Scrapy crawler)
- extruct (schema extraction)
- PageSpeed Insights API (free key)
- Common Crawl (backlinks estimate)
- Google Places API (GBP audit)
- YouTube Data API v3 (social activity)
- Playwright (screenshots)
- Jinja2 + WeasyPrint (HTML + PDF)

## Deploy to Hugging Face Spaces

1. Create a new Space: Docker, public.
2. Push this directory to the Space repo.
3. Set Secrets in the Space settings:
   - `PAGESPEED_API_KEY`
   - `YOUTUBE_API_KEY`
   - `GOOGLE_PLACES_API_KEY`
   - `ALLOWED_ORIGIN` → `https://baheesafatima.com`
4. Hugging Face builds and runs the Dockerfile automatically.
5. Your API will be at `https://<username>-seo-audit.hf.space`.

## Local dev

```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
uvicorn app.main:app --reload --port 8000
```

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/audit` | Start audit (form: `url`, optional `gbp_url`, optional `keyword_csv`) |
| GET | `/audit/{id}` | Poll status |
| GET | `/report/{id}` | Download HTML report |
| GET | `/report/{id}/pdf` | Download PDF report |
| POST | `/audit/{id}/confirm-competitors` | Confirm competitor URLs and run comparison |

## Build order (spec)
- [x] Crawler module
- [x] PageSpeed + schema + indexing collectors
- [x] Scoring engine (26 elements, 3 categories)
- [x] HTML report (Jinja2) + PDF (WeasyPrint)
- [x] Screenshots (Playwright)
- [x] Social profile detection
- [x] GBP collector (Places API)
- [x] NAP consistency
- [x] AI Readiness scoring
- [x] Backlinks (Common Crawl estimate)
- [x] Keyword module (free + CSV modes)
- [x] Competitor module (suggest + confirm + compare)
- [x] FastAPI + Docker for Hugging Face Spaces
