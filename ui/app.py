"""FastAPI web application and REST API for Opportunity & Job Scraper."""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

from scrapers.job_scraper import JobScraper
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from parsers.scholarship_parser import parse_post
from storage.db import OpportunityDB

app = FastAPI(
    title="Opportunity & Job Scraper API",
    description="REST API and Interactive Web Dashboard for Scholarships and 4-Day Remote Jobs",
    version="1.0.0",
)

db = OpportunityDB()
TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.get("/")
def serve_dashboard():
    """Serves the interactive web dashboard."""
    html_file = TEMPLATES_DIR / "index.html"
    return FileResponse(html_file)


@app.get("/api/stats")
def get_stats():
    """Returns database summary counts."""
    return {
        "scholarships_count": db.count(),
        "jobs_count": db.count_jobs(),
    }


@app.get("/api/opportunities")
def get_opportunities(
    search: Optional[str] = None,
    country: Optional[str] = None,
    level: Optional[str] = None,
    closing_soon: bool = False,
    days: int = 60,
    sort_by: str = "date",
    order: str = "desc",
):
    """Retrieves and filters scholarship opportunities."""
    if closing_soon:
        items = db.get_closing_soon(days=days)
    else:
        items = db.filter_opportunities(
            keyword=search,
            country=country,
            level=level,
            sort_by=sort_by,
            order=order,
            limit=100,
        )
    return items


@app.get("/api/jobs")
def get_jobs(
    search: Optional[str] = None,
    has_salary: bool = False,
    remote_only: bool = False,
    min_score: Optional[int] = None,
    sort_by: str = "id",
    order: str = "desc",
):
    """Retrieves and filters job listings."""
    jobs = db.filter_jobs(
        keyword=search,
        has_salary=has_salary,
        remote_only=remote_only,
        min_score=min_score,
        sort_by=sort_by,
        order=order,
        limit=100,
    )
    return jobs


@app.post("/api/scrape/jobs")
def scrape_jobs():
    """Triggers live scraping of 4dayweek.io remote jobs."""
    try:
        scraper = JobScraper()
        jobs = scraper.scrape_4dayweek(limit=50)
        new_count = sum(1 for j in jobs if db.save_job(j))
        return {
            "success": True,
            "scraped": len(jobs),
            "new_inserted": new_count,
            "total_now": db.count_jobs(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/scrape/scholarships")
def scrape_scholarships():
    """Triggers live scraping of Telegram scholarship channel."""
    try:
        tg_scraper = TelegramScraper()
        web_scraper = WebScraper()
        raw_posts = tg_scraper.scrape_channel("https://t.me/OHUB4AllET", limit=8)

        new_count = 0
        for p in raw_posts:
            item = parse_post(p)
            portal = None
            highlights = None

            if item.is_opportunity and item.apply_url and not item.apply_url.rstrip("/").endswith("/opportunities"):
                try:
                    page_data = web_scraper.scrape(item.apply_url)
                    portal = page_data.apply_links[0] if page_data.apply_links else None
                    highlights = page_data.key_highlights
                except Exception:
                    pass

            is_new = db.save_opportunity(item, official_portal=portal, key_highlights=highlights)
            if is_new:
                new_count += 1

        return {
            "success": True,
            "scraped": len(raw_posts),
            "new_inserted": new_count,
            "total_now": db.count(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
