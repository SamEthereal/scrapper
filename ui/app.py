"""FastAPI web application and REST API for Opportunity & Job Scraper."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from scrapers.job_scraper import JobScraper
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from parsers.scholarship_parser import parse_post
from storage.db import OpportunityDB
from services.matcher import ProfileMatcher
from services.copilot import ApplicationCopilot


class PipelineItemCreate(BaseModel):
    item_type: str  # 'opportunity' or 'job'
    item_id: int
    title: str
    subtitle: Optional[str] = None
    deadline_or_salary: Optional[str] = None
    deadline_date: Optional[str] = None
    url: Optional[str] = None
    status: str = "saved"
    notes: str = ""


class PipelineItemUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class UserProfileUpdate(BaseModel):
    full_name: str
    email: Optional[str] = None
    title: Optional[str] = None
    skills: str = ""
    degree: Optional[str] = None
    experience_years: int = 0
    preferred_locations: Optional[str] = None
    target_roles: Optional[str] = None
    bio: Optional[str] = None


class CopilotGenerateRequest(BaseModel):
    item_type: str  # 'job' or 'opportunity'
    item_id: int
    tone: str = "professional"

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


@app.get("/api/history")
def get_history():
    """Returns recent scraper activity log entries for the history panel."""
    log_file = Path("scraper_activity.log")
    if not log_file.exists():
        return []
    lines = [line.strip() for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[-12:]


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
    """Retrieves and filters scholarship opportunities with AI match scoring."""
    db_sort = sort_by if sort_by != "match" else "date"
    if closing_soon:
        items = db.get_closing_soon(days=days)
    else:
        items = db.filter_opportunities(
            keyword=search,
            country=country,
            level=level,
            sort_by=db_sort,
            order=order,
            limit=100,
        )

    profile = db.get_user_profile()
    enriched = ProfileMatcher.enrich_items(profile, items, item_type="opportunity")
    if sort_by == "match":
        enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=(order != "asc"))
    return enriched


@app.get("/api/jobs")
def get_jobs(
    search: Optional[str] = None,
    has_salary: bool = False,
    remote_only: bool = False,
    min_score: Optional[int] = None,
    sort_by: str = "id",
    order: str = "desc",
):
    """Retrieves and filters job listings with AI match scoring."""
    db_sort = sort_by if sort_by != "match" else "id"
    jobs = db.filter_jobs(
        keyword=search,
        has_salary=has_salary,
        remote_only=remote_only,
        min_score=min_score,
        sort_by=db_sort,
        order=order,
        limit=100,
    )

    profile = db.get_user_profile()
    enriched = ProfileMatcher.enrich_items(profile, jobs, item_type="job")
    if sort_by == "match":
        enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=(order != "asc"))
    return enriched


# =============================================================================
# Milestone 11: User Profile & 1-Click Application Copilot Endpoints
# =============================================================================

@app.get("/api/profile")
def get_profile():
    """Returns the current user profile, skills, and matching preferences."""
    return db.get_user_profile()


@app.post("/api/profile")
def update_profile(profile_data: UserProfileUpdate):
    """Updates user skills, target roles, education, and preferences."""
    updated = db.save_user_profile(
        full_name=profile_data.full_name,
        email=profile_data.email,
        title=profile_data.title,
        skills=profile_data.skills,
        degree=profile_data.degree,
        experience_years=profile_data.experience_years,
        preferred_locations=profile_data.preferred_locations,
        target_roles=profile_data.target_roles,
        bio=profile_data.bio,
    )
    return {"success": True, "profile": updated}


@app.post("/api/copilot/generate")
def generate_application_copilot(req: CopilotGenerateRequest):
    """Generates a tailored Cover Letter or Statement of Purpose for a listing."""
    profile = db.get_user_profile()

    if req.item_type == "job":
        item = db.get_job_by_id(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Job listing not found")
    else:
        item = db.get_opportunity_by_id(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Scholarship opportunity not found")

    document = ApplicationCopilot.generate_document(
        profile=profile,
        item=item,
        item_type=req.item_type,
        tone=req.tone,
    )
    return {"success": True, "document": document}


@app.get("/api/pipeline")
def get_pipeline():
    """Returns all tracked applications in the user's pipeline."""
    return db.get_pipeline()


@app.post("/api/pipeline")
def add_to_pipeline(item: PipelineItemCreate):
    """Adds or updates an opportunity/job in the application pipeline."""
    return db.add_to_pipeline(
        item_type=item.item_type,
        item_id=item.item_id,
        title=item.title,
        subtitle=item.subtitle,
        deadline_or_salary=item.deadline_or_salary,
        deadline_date=item.deadline_date,
        url=item.url,
        status=item.status,
        notes=item.notes,
    )


@app.patch("/api/pipeline/{app_id}")
def update_pipeline(app_id: int, item: PipelineItemUpdate):
    """Updates an application status or notes in the pipeline."""
    success = db.update_pipeline_item(app_id, status=item.status, notes=item.notes)
    if not success:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    return {"success": True}


@app.delete("/api/pipeline/{app_id}")
def delete_pipeline(app_id: int):
    """Removes an application from the pipeline."""
    success = db.delete_pipeline_item(app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    return {"success": True}


@app.get("/api/calendar/{opp_id}.ics")
def export_calendar_event(opp_id: int):
    """Generates an RFC 5545 iCalendar (.ics) file for an opportunity deadline with alarms."""
    opp = db.get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    deadline_str = opp.get("deadline_date") or opp.get("deadline") or ""
    dt_clean = None
    if deadline_str and len(deadline_str) >= 10:
        try:
            dt = datetime.strptime(deadline_str[:10], "%Y-%m-%d")
            dt_clean = dt.strftime("%Y%m%d")
            dt_end = (dt + timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            pass

    if not dt_clean:
        now = datetime.utcnow()
        dt_clean = now.strftime("%Y%m%d")
        dt_end = (now + timedelta(days=1)).strftime("%Y%m%d")

    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    title = (opp.get("title") or "Opportunity Deadline").replace("\n", " ").strip()
    url = opp.get("official_portal") or opp.get("apply_url") or "https://t.me/OHUB4AllET"
    summary = f"⏰ Application Deadline: {title}"
    description = f"Application deadline for {title}.\\n\\nApply here: {url}\\n\\nTracked via ScraperGalore."

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//ScraperGalore//Application Tracker//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:opp-{opp_id}-deadline@scrapergalore\r\n"
        f"DTSTAMP:{now_stamp}\r\n"
        f"DTSTART;VALUE=DATE:{dt_clean}\r\n"
        f"DTEND;VALUE=DATE:{dt_end}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"URL:{url}\r\n"
        "STATUS:CONFIRMED\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-P3D\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:Reminder: 3 days left before application deadline for {title}!\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="deadline_opp_{opp_id}.ics"',
            "Cache-Control": "no-cache",
        },
    )


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
