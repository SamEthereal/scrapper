"""FastAPI web application and REST API for Opportunity & Job Scraper."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile, File, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

from scrapers.job_scraper import JobScraper
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from scrapers.wwr_scraper import WWRScraper
from scrapers.grant_scraper import GrantScraper
from scrapers.universal_scraper import UniversalScraper
from scrapers.local_jobs_scraper import LocalJobsScraper
from scrapers.scholarship_directory_scraper import ScholarshipDirectoryScraper
from scrapers.ohub_web_scraper import OHUBWebScraper
from parsers.scholarship_parser import parse_post
from storage.db import OpportunityDB
from services.matcher import ProfileMatcher
from services.copilot import ApplicationCopilot
from services.telegram_bot import TelegramAlertDispatcher
from services.ai_resume import AIResumeService
from services.scheduler import AutonomousScheduler
from services.auth import (
    COOKIE_NAME,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    extract_token_from_request,
)


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
    user_id: Optional[str] = None


class PipelineItemUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class TelegramSendRequest(BaseModel):
    item_type: str  # 'job', 'opportunity', 'grant'
    item_id: int


class UserProfileUpdate(BaseModel):
    full_name: str
    email: Optional[str] = None
    user_id: Optional[str] = None
    title: Optional[str] = None
    field_of_study: Optional[str] = None
    degree: Optional[str] = None
    skills: str = ""
    experience_years: int = 0
    preferred_locations: Optional[str] = None
    target_roles: Optional[str] = None
    bio: Optional[str] = None
    telegram_handle: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    gpa_grades: Optional[str] = None


class CopilotGenerateRequest(BaseModel):
    item_type: str  # 'job' or 'opportunity'
    item_id: int
    tone: str = "professional"


class CustomSourceCreate(BaseModel):
    name: str
    url: str
    source_type: str  # 'rss', 'telegram', 'web'
    category: str     # 'jobs', 'scholarships', 'grants'


class ResumeParseTextRequest(BaseModel):
    resume_text: str
    api_key: Optional[str] = None


class ResumeApplyRequest(BaseModel):
    extracted_data: dict
    resume_raw: Optional[str] = None


class GeminiKeyRequest(BaseModel):
    api_key: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    persona: str = "all"  # 'student', 'job_seeker', 'all'


class LoginRequest(BaseModel):
    email: str
    password: str


class PersonaUpdateRequest(BaseModel):
    persona: str


class SchedulerToggleRequest(BaseModel):
    enabled: Optional[bool] = None


class SchedulerConfigRequest(BaseModel):
    interval_hours: Optional[int] = None
    auto_telegram: Optional[bool] = None
    min_score_threshold: Optional[int] = None


app = FastAPI(
    title="Opportunity & Job Scraper API",
    description="REST API and Interactive Web Dashboard for Scholarships and 4-Day Remote Jobs",
    version="1.0.0",
)

db = OpportunityDB()
scheduler_service = AutonomousScheduler(db)
TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.on_event("startup")
def startup_event():
    """Starts background autonomous radar scheduler."""
    scheduler_service.start()


@app.on_event("shutdown")
def shutdown_event():
    """Cleanly stops background autonomous radar scheduler."""
    scheduler_service.stop()


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
        "grants_count": db.count_grants(),
        "pipeline_count": len(db.get_pipeline()),
    }


# =========================================================================
# Phase 1 & Option A: Authentication, Supabase Config & 3-Persona Management
# =========================================================================

@app.get("/api/auth/config")
def get_auth_config():
    """Returns frontend authentication configuration (Supabase public credentials)."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    return {
        "supabase_url": supabase_url,
        "supabase_anon_key": supabase_key,
        "has_supabase": bool(supabase_url and supabase_key),
    }


@app.post("/api/auth/register")
def register_user(req: RegisterRequest, response: Response):
    """Registers a new user and issues a secure HttpOnly JWT session cookie."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    if not req.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")

    valid_personas = {"student", "job_seeker", "all"}
    persona = req.persona if req.persona in valid_personas else "all"

    existing = db.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    hashed = hash_password(req.password)
    user = db.create_user(
        email=email,
        hashed_password=hashed,
        full_name=req.full_name,
        persona=persona,
    )

    token = create_access_token({
        "sub": str(user["id"]),
        "email": user["email"],
        "persona": user["persona"],
    })

    # Set secure HttpOnly session cookie (7-day validity)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=False,
    )

    return {
        "success": True,
        "user": user,
        "token": token,
        "message": "Account created successfully",
    }


@app.post("/api/auth/login")
def login_user(req: LoginRequest, response: Response):
    """Authenticates user credentials and issues an HttpOnly session cookie."""
    email = req.email.strip().lower()
    user = db.get_user_by_email(email)
    if not user or not verify_password(req.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db.update_user_last_login(user["id"])

    user_clean = {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "persona": user["persona"],
        "role": user["role"],
        "created_at": user.get("created_at"),
    }

    token = create_access_token({
        "sub": str(user["id"]),
        "email": user["email"],
        "persona": user["persona"],
    })

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        secure=False,
    )

    return {
        "success": True,
        "user": user_clean,
        "token": token,
        "message": "Signed in successfully",
    }


@app.post("/api/auth/logout")
def logout_user(response: Response):
    """Clears the authentication session cookie."""
    response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite="lax")
    return {"success": True, "message": "Logged out successfully"}


def resolve_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Resolves active user from JWT session cookie, Bearer header, or X-User headers."""
    # 1. Native JWT token from cookie or Authorization header
    token = extract_token_from_request(request)
    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            try:
                user_id = int(payload["sub"])
                u = db.get_user_by_id(user_id)
                if u:
                    return u
            except Exception:
                pass
            if payload.get("email"):
                u = db.get_user_by_email(payload["email"])
                if u:
                    return u

    # 2. X-User-Email / X-User-Id header (e.g. from Supabase frontend session or client headers)
    user_email = request.headers.get("X-User-Email") or request.query_params.get("user_email")
    user_id_hdr = request.headers.get("X-User-Id") or request.query_params.get("user_id")

    if user_email:
        clean_email = user_email.strip().lower()
        u = db.get_user_by_email(clean_email)
        if u:
            return u
        # User signed up via Supabase and exists in Supabase, but not yet in SQLite users table:
        # Auto-provision them in SQLite
        user_name = request.headers.get("X-User-Name") or clean_email.split("@")[0]
        try:
            created = db.create_user(
                email=clean_email,
                hashed_password="SUPABASE_OAUTH_USER",
                full_name=user_name,
                persona="all",
            )
            return created
        except Exception:
            return db.get_user_by_email(clean_email)

    if user_id_hdr:
        try:
            u = db.get_user_by_id(int(user_id_hdr))
            if u:
                return u
        except Exception:
            pass

    return None


@app.get("/api/auth/me")
def get_current_user(request: Request):
    """Returns the authenticated user info or unauthenticated status."""
    user = resolve_current_user(request)
    if not user:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "persona": user.get("persona", "all"),
            "role": user.get("role", "user"),
        },
    }


@app.put("/api/auth/persona")
def update_persona(req: PersonaUpdateRequest, request: Request, response: Response):
    """Updates user persona preference and re-issues an updated JWT cookie."""
    valid_personas = {"student", "job_seeker", "all"}
    if req.persona not in valid_personas:
        raise HTTPException(status_code=400, detail="Invalid persona choice")

    token = extract_token_from_request(request)
    user = None
    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            user = db.get_user_by_id(int(payload["sub"]))

    if user:
        db.update_user_persona(user["id"], req.persona)
        user["persona"] = req.persona
        new_token = create_access_token({
            "sub": str(user["id"]),
            "email": user["email"],
            "persona": req.persona,
        })
        response.set_cookie(
            key=COOKIE_NAME,
            value=new_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
            secure=False,
        )

    return {"success": True, "persona": req.persona}


@app.get("/api/sources")
def get_sources():
    """Returns real-time status and metrics of all configured scraping engines."""
    all_jobs = db.get_jobs(limit=1000)
    wwr_count = sum(1 for j in all_jobs if j.get("source") == "WeWorkRemotely")
    day4_count = sum(1 for j in all_jobs if j.get("source") == "4dayweek.io")
    remoteok_count = sum(1 for j in all_jobs if j.get("source") == "RemoteOK")
    ethiojobs_count = sum(1 for j in all_jobs if "Ethiojobs" in j.get("source", "") or "Reporter" in j.get("source", ""))
    elelan_count = sum(1 for j in all_jobs if j.get("source") == "Elelan Jobs")

    all_opps = db.get_all(limit=1000)
    ohub_count = sum(1 for o in all_opps if "OHUB" in o.get("channel_name", ""))
    scholars4dev_count = sum(1 for o in all_opps if o.get("channel_name") == "Scholars4Dev")
    ethio_tg_count = sum(1 for o in all_opps if "ethioscholarship" in o.get("channel_name", "").lower())
    carraa_count = sum(1 for o in all_opps if o.get("channel_name") == "Carraadesk")

    return [
        {
            "id": "ohub_portal",
            "name": "OHUB Opportunities Web Portal",
            "target": "https://opportunities.ohubet.com",
            "category": "Scholarships, Fellowships & Internships",
            "count": ohub_count or db.count(),
            "status": "online",
            "mode": "Structured Web Portal Crawler",
            "endpoint": "/api/scrape/ohub/all",
            "icon": "fa-globe",
            "color": "indigo",
            "desc": "Direct web portal scraping verified Scholarships, Fellowships, Internships, and Jobs."
        },
        {
            "id": "scholars4dev",
            "name": "Scholars4Dev (Ethiopians & Developing)",
            "target": "https://www.scholars4dev.com/tag/scholarships-for-ethiopians/",
            "category": "Curated Global Scholarships",
            "count": scholars4dev_count,
            "status": "online",
            "mode": "Two-Tier Directory Crawler",
            "endpoint": "/api/scrape/curated/scholars4dev",
            "icon": "fa-graduation-cap",
            "color": "blue",
            "desc": "Clean, fully-funded Masters & PhD awards with explicit country eligibility and deadlines."
        },
        {
            "id": "ethio_scholarships",
            "name": "Ethio Scholarship Telegram",
            "target": "https://t.me/ethioscholarshipopportunity",
            "category": "Telegram Scholarship Feed",
            "count": ethio_tg_count,
            "status": "online",
            "mode": "Zero-Credential Public Stream",
            "endpoint": "/api/scrape/curated/ethio-scholarships",
            "icon": "fa-paper-plane",
            "color": "cyan",
            "desc": "Verified Ethiopian student scholarship opportunities, fellowships, and entrance exams."
        },
        {
            "id": "jobs_ethiojobs",
            "name": "Ethiojobs (Ethiopia #1 Board)",
            "target": "https://www.ethiojobs.net/jobs",
            "category": "Local Ethiopian Jobs",
            "count": ethiojobs_count,
            "status": "online",
            "mode": "Structured Category Crawler",
            "endpoint": "/api/scrape/curated/ethiojobs",
            "icon": "fa-briefcase",
            "color": "emerald",
            "desc": "Ethiopia's premier employment board with categorized tech, finance, and engineering openings."
        },
        {
            "id": "jobs_elelan",
            "name": "Elelan Jobs (Addis Ababa)",
            "target": "https://elelanjobs.com/",
            "category": "Local Ethiopian Jobs",
            "count": elelan_count,
            "status": "online",
            "mode": "Two-Tier Detail Scraper",
            "endpoint": "/api/scrape/curated/elelan",
            "icon": "fa-building",
            "color": "teal",
            "desc": "Two-tier crawler extracting verified requirements, company contacts, and application deadlines."
        },
        {
            "id": "jobs_remoteok",
            "name": "RemoteOK International Tech",
            "target": "https://remoteok.com/api",
            "category": "Foreign Tech & Engineering",
            "count": remoteok_count,
            "status": "online",
            "mode": "Open Developer JSON API",
            "endpoint": "/api/scrape/curated/remoteok",
            "icon": "fa-laptop-code",
            "color": "rose",
            "desc": "High-paying global remote software engineering, DevOps, and AI developer jobs."
        },
        {
            "id": "jobs_4dayweek",
            "name": "4-Day Week Remote Jobs",
            "target": "https://4dayweek.io/remote-jobs",
            "category": "Work-Life Balance Jobs",
            "count": day4_count,
            "status": "online",
            "mode": "DOM Card Scraper",
            "endpoint": "/api/scrape/jobs",
            "icon": "fa-clock",
            "color": "emerald",
            "desc": "Extracts reduced-work-week developer & tech roles with work-life balance ratings."
        },
        {
            "id": "jobs_wwr",
            "name": "WeWorkRemotely Tech Gigs",
            "target": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "category": "Remote Developers & Gigs",
            "count": wwr_count,
            "status": "online",
            "mode": "Public XML RSS Feed",
            "endpoint": "/api/scrape/wwr",
            "icon": "fa-globe",
            "color": "amber",
            "desc": "Ingests remote engineering, full-stack, and contractor postings across global timezones."
        },
        {
            "id": "carraadesk",
            "name": "Carraadesk Quality Gate",
            "target": "https://carraadesk.com/",
            "category": "Dual Opportunities & Jobs",
            "count": carraa_count,
            "status": "online",
            "mode": "Smart Intent Classifier",
            "endpoint": "/api/scrape/curated/carraadesk",
            "icon": "fa-filter",
            "color": "violet",
            "desc": "Strictly gates articles: routes scholarships to opportunities and jobs to vacancies, dropping noise."
        },
        {
            "id": "tech_grants",
            "name": "Tech Grants & Accelerators",
            "target": "YC, Techstars, Mozilla, EU Horizon, AWS",
            "category": "Grants & Non-Dilutive Capital",
            "count": db.count_grants(),
            "status": "online",
            "mode": "Verified Venture Radar",
            "endpoint": "/api/scrape/grants",
            "icon": "fa-rocket",
            "color": "purple",
            "desc": "Tracks non-dilutive innovation grants, startup batches, and AI compute credits."
        }
    ]


@app.get("/api/grants")
def get_grants(
    request: Request,
    search: Optional[str] = None,
    sort_by: str = "id",
    order: str = "desc",
    tailored_only: bool = False,
):
    """Retrieves and filters tech grants and accelerators with AI match scoring."""
    grants = db.get_grants(limit=100, keyword=search)
    curr = resolve_current_user(request)
    profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)
    enriched = ProfileMatcher.enrich_items(profile, grants, item_type="grant")
    if tailored_only:
        enriched = [x for x in enriched if x.get("domain_match", True)]
    if sort_by == "match":
        enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=(order != "asc"))
    return enriched


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
    request: Request,
    search: Optional[str] = None,
    country: Optional[str] = None,
    level: Optional[str] = None,
    funding_type: Optional[str] = None,
    closing_soon: bool = False,
    days: int = 60,
    sort_by: str = "date",
    order: str = "desc",
    tailored_only: bool = False,
):
    """Retrieves and filters scholarship opportunities with AI match scoring and degree alignment."""
    db_sort = sort_by if sort_by != "match" else "date"
    if closing_soon:
        items = db.get_closing_soon(days=days)
    else:
        items = db.filter_opportunities(
            keyword=search,
            country=country,
            level=level,
            funding_type=funding_type,
            sort_by=db_sort,
            order=order,
            limit=100,
        )

    curr = resolve_current_user(request)
    profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)
    enriched = ProfileMatcher.enrich_items(profile, items, item_type="opportunity", sort_by_relevance=(sort_by != "date"))
    if tailored_only:
        enriched = [x for x in enriched if x.get("domain_match", True)]
    if sort_by == "match":
        enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=(order != "asc"))
    return enriched


@app.get("/api/jobs")
def get_jobs(
    request: Request,
    search: Optional[str] = None,
    experience_level: Optional[str] = None,
    category: Optional[str] = None,
    job_type: Optional[str] = None,
    has_salary: bool = False,
    remote_only: bool = False,
    min_score: Optional[int] = None,
    sort_by: str = "id",
    order: str = "desc",
    tailored_only: bool = False,
):
    """Retrieves and filters job listings with AI match scoring and domain relevance ranking."""
    db_sort = sort_by if sort_by != "match" else "id"
    jobs = db.filter_jobs(
        keyword=search,
        experience_level=experience_level,
        category=category,
        job_type=job_type,
        has_salary=has_salary,
        remote_only=remote_only,
        min_score=min_score,
        sort_by=db_sort,
        order=order,
        limit=100,
    )

    curr = resolve_current_user(request)
    profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)
    enriched = ProfileMatcher.enrich_items(profile, jobs, item_type="job", sort_by_relevance=(sort_by != "date"))
    if tailored_only:
        enriched = [x for x in enriched if x.get("domain_match", True)]
    if sort_by == "match":
        enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=(order != "asc"))
    return enriched


# =============================================================================
# Milestone 11: Multi-User Profile & 1-Click Application Copilot Endpoints
# =============================================================================

@app.get("/api/profile")
def get_profile(request: Request):
    """Returns the current user profile, skills, and matching preferences."""
    curr = resolve_current_user(request)
    if curr:
        return db.get_user_profile(user_id=str(curr["id"]), email=curr.get("email"))
    return db.get_user_profile()


@app.post("/api/profile")
def update_profile(profile_data: UserProfileUpdate, request: Request):
    """Updates user skills, target roles, education, field of study, and preferences."""
    curr = resolve_current_user(request)
    user_id = profile_data.user_id or (str(curr["id"]) if curr else None)
    email = profile_data.email or (curr.get("email") if curr else None)

    updated = db.save_user_profile(
        full_name=profile_data.full_name,
        email=email,
        user_id=user_id,
        title=profile_data.title,
        field_of_study=profile_data.field_of_study,
        degree=profile_data.degree,
        skills=profile_data.skills,
        experience_years=profile_data.experience_years,
        preferred_locations=profile_data.preferred_locations,
        target_roles=profile_data.target_roles,
        bio=profile_data.bio,
        telegram_handle=profile_data.telegram_handle,
        telegram_chat_id=profile_data.telegram_chat_id,
        gpa_grades=profile_data.gpa_grades,
    )
    return {"success": True, "profile": updated}


@app.post("/api/copilot/generate")
def generate_application_copilot(req: CopilotGenerateRequest, request: Request):
    """Generates a tailored Cover Letter or Statement of Purpose for a listing."""
    curr = resolve_current_user(request)
    profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)

    if req.item_type == "job":
        item = db.get_job_by_id(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Job listing not found")
    elif req.item_type == "grant":
        item = db.get_grant_by_id(req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Grant listing not found")
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
    return {
        "success": True,
        "document": document,
        "title": document.get("title"),
        "markdown": document.get("markdown"),
        "plain_text": document.get("plain_text"),
        "score": document.get("score"),
    }


@app.get("/api/pipeline")
def get_pipeline(request: Request):
    """Returns all tracked applications in the user's pipeline."""
    curr = resolve_current_user(request)
    user_id = str(curr["id"]) if curr else "1"
    return db.get_pipeline(user_id=user_id)


@app.post("/api/pipeline")
def add_to_pipeline(item: PipelineItemCreate, request: Request):
    """Adds or updates an opportunity/job in the application pipeline."""
    curr = resolve_current_user(request)
    user_id = item.user_id or (str(curr["id"]) if curr else "1")
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
        user_id=user_id,
    )


@app.patch("/api/pipeline/{app_id}")
def update_pipeline(app_id: int, item: PipelineItemUpdate, request: Request):
    """Updates an application status or notes in the pipeline."""
    curr = resolve_current_user(request)
    user_id = str(curr["id"]) if curr else None
    success = db.update_pipeline_item(app_id, status=item.status, notes=item.notes, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    return {"success": True}


@app.delete("/api/pipeline/{app_id}")
def delete_pipeline(app_id: int, request: Request):
    """Removes an application from the pipeline."""
    curr = resolve_current_user(request)
    user_id = str(curr["id"]) if curr else None
    success = db.delete_pipeline_item(app_id, user_id=user_id)
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


# =============================================================================
# Milestone 13: Telegram Alert Dispatcher Endpoints
# =============================================================================

telegram_dispatcher = TelegramAlertDispatcher(db)


@app.get("/api/telegram/status")
def get_telegram_status():
    """Returns current Telegram Bot connection state and target chat ID."""
    return telegram_dispatcher.get_bot_info()


@app.post("/api/telegram/detect")
def detect_telegram_chat():
    """Polls Telegram updates to auto-link the chat ID of the user who clicked Start."""
    return telegram_dispatcher.detect_chat_id()


@app.post("/api/telegram/test")
def test_telegram_connection():
    """Dispatches a test verification alert card to the connected phone."""
    return telegram_dispatcher.test_connection()


@app.post("/api/telegram/send")
def send_telegram_alert(payload: TelegramSendRequest, request: Request):
    """Sends a specific opportunity, job, or grant card directly to the user's Telegram."""
    curr = resolve_current_user(request)
    profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)

    if payload.item_type == "job":
        item = db.get_job_by_id(payload.item_id)
    elif payload.item_type == "grant":
        item = db.get_grant_by_id(payload.item_id)
    else:
        item = db.get_opportunity_by_id(payload.item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    match = ProfileMatcher.match_item(profile, item, item_type=payload.item_type)
    target_chat = profile.get("telegram_chat_id") or None
    return telegram_dispatcher.send_opportunity_card(item, item_type=payload.item_type, match=match, chat_id=target_chat)


# =============================================================================
# Option 2: Autonomous Scheduler & Crawl Audit History API
# =============================================================================

@app.get("/api/scheduler/status")
def get_scheduler_status():
    """Returns runtime state, scheduled intervals, and performance metrics."""
    return scheduler_service.get_status()


@app.post("/api/scheduler/toggle")
def toggle_scheduler(payload: Optional[SchedulerToggleRequest] = None):
    """Enables or pauses autonomous background recurring crawling."""
    if payload is not None and payload.enabled is not None:
        scheduler_service.enabled = payload.enabled
    else:
        scheduler_service.enabled = not scheduler_service.enabled
    db.set_setting("scheduler_enabled", "true" if scheduler_service.enabled else "false")
    return {
        "success": True,
        "enabled": scheduler_service.enabled,
        "message": f"Autonomous scheduler {'activated' if scheduler_service.enabled else 'paused'}.",
    }


@app.put("/api/scheduler/config")
def update_scheduler_config(payload: SchedulerConfigRequest):
    """Updates crawl interval and automated Telegram radar threshold."""
    if payload.interval_hours is not None:
        scheduler_service.interval_hours = payload.interval_hours
        db.set_setting("scheduler_interval_hours", str(payload.interval_hours))
    if payload.auto_telegram is not None:
        scheduler_service.auto_telegram = payload.auto_telegram
        db.set_setting("scheduler_auto_telegram", "true" if payload.auto_telegram else "false")
    if payload.min_score_threshold is not None:
        scheduler_service.min_score_threshold = payload.min_score_threshold
        db.set_setting("scheduler_min_score", str(payload.min_score_threshold))
    return {
        "success": True,
        "interval_hours": scheduler_service.interval_hours,
        "auto_telegram": scheduler_service.auto_telegram,
        "min_score_threshold": scheduler_service.min_score_threshold,
    }


@app.post("/api/scheduler/run-now")
def trigger_scheduler_run_now():
    """Triggers an immediate autonomous radar scan across all configured feeds."""
    result = scheduler_service.trigger_now(triggered_by="manual_ui")
    return result


@app.get("/api/scheduler/history")
def get_scheduler_history(limit: int = Query(default=50, ge=1, le=200)):
    """Returns execution history log of recent crawler runs."""
    return db.get_crawl_history(limit=limit)


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


@app.post("/api/scrape/wwr")
def scrape_wwr_jobs():
    """Triggers live scraping of WeWorkRemotely developer jobs & gigs."""
    try:
        scraper = WWRScraper()
        jobs = scraper.scrape(limit=50)
        new_count = sum(1 for j in jobs if db.save_job(j))
        return {
            "success": True,
            "scraped": len(jobs),
            "new_inserted": new_count,
            "total_now": db.count_jobs(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/scrape/grants")
def scrape_tech_grants():
    """Triggers live indexing of Tech Grants, Accelerators & AI Compute credits."""
    try:
        scraper = GrantScraper()
        grants = scraper.scrape(limit=30)
        new_count = sum(1 for g in grants if db.save_grant(g))
        return {
            "success": True,
            "scraped": len(grants),
            "new_inserted": new_count,
            "total_now": db.count_grants(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# Curated Multi-Source Scrapers (OHUB Web, Ethiojobs, Elelan, RemoteOK, Scholars4Dev, etc.)
# =============================================================================

@app.post("/api/scrape/ohub/all")
def scrape_ohub_all():
    """Triggers scraping of all 4 categories on opportunities.ohubet.com."""
    scraper = OHUBWebScraper(db)
    result = scraper.scrape_all_categories(limit_per_cat=8)
    return result


@app.post("/api/scrape/ohub/{category}")
def scrape_ohub_category(category: str):
    """Triggers scraping of a specific category (scholarships, fellowships, internships, jobs) on OHUB."""
    scraper = OHUBWebScraper(db)
    result = scraper.scrape_category(category_key=category, limit=12)
    return result


@app.post("/api/scrape/curated/ethiojobs")
def scrape_curated_ethiojobs():
    """Triggers scraping of Ethiojobs premier listings."""
    scraper = LocalJobsScraper(db)
    result = scraper.scrape_ethiojobs(limit=15)
    return result


@app.post("/api/scrape/curated/reporter")
def scrape_curated_reporter():
    """Triggers live scraping of Ethiopian Reporter Jobs."""
    scraper = LocalJobsScraper(db)
    result = scraper.scrape_reporter_jobs(limit=15)
    return result


@app.post("/api/scrape/curated/elelan")
def scrape_curated_elelan():
    """Triggers two-tier scraping of Elelan Jobs."""
    scraper = LocalJobsScraper(db)
    result = scraper.scrape_elelan_jobs(limit=10)
    return result


@app.post("/api/scrape/curated/remoteok")
def scrape_curated_remoteok():
    """Triggers scraping of RemoteOK global engineering and developer roles."""
    scraper = LocalJobsScraper(db)
    result = scraper.scrape_remoteok(limit=25)
    return result


@app.post("/api/scrape/curated/scholars4dev")
def scrape_curated_scholars4dev():
    """Triggers two-tier scraping of Scholars4Dev opportunities."""
    scraper = ScholarshipDirectoryScraper(db)
    result = scraper.scrape_scholars4dev(limit=10)
    return result


@app.post("/api/scrape/curated/ethio-scholarships")
def scrape_curated_ethio_scholarships():
    """Triggers live zero-credential scraping of @ethioscholarshipopportunity."""
    scraper = ScholarshipDirectoryScraper(db)
    result = scraper.scrape_ethio_scholarship_telegram(limit=15)
    return result


@app.post("/api/scrape/curated/carraadesk")
def scrape_curated_carraadesk():
    """Triggers quality-gated dual scraping of Carraadesk."""
    scraper = ScholarshipDirectoryScraper(db)
    result = scraper.scrape_carraadesk(limit=10)
    return result


# =============================================================================
# Milestone 14: Universal Feed Studio — Custom Sources API
# =============================================================================

@app.get("/api/custom-sources")
def get_custom_sources():
    """Returns all user-defined custom scraping sources."""
    return db.get_custom_sources()


@app.post("/api/custom-sources")
def add_custom_source(source: CustomSourceCreate):
    """Adds a new custom scraping source to the Universal Feed Studio."""
    try:
        created = db.add_custom_source(
            name=source.name,
            url=source.url,
            source_type=source.source_type,
            category=source.category,
        )
        return {"success": True, "source": created}
    except Exception as e:
        if "UNIQUE" in str(e).upper():
            return JSONResponse(status_code=409, content={"success": False, "error": "A source with this URL already exists."})
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.delete("/api/custom-sources/{source_id}")
def delete_custom_source(source_id: int):
    """Removes a custom source from the Universal Feed Studio."""
    success = db.delete_custom_source(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Custom source not found")
    return {"success": True}


@app.patch("/api/custom-sources/{source_id}/toggle")
def toggle_custom_source(source_id: int):
    """Toggles a custom source between active and inactive."""
    result = db.toggle_custom_source(source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Custom source not found")
    return {"success": True, "source": result}


@app.post("/api/scrape/custom/{source_id}")
def scrape_custom_source(source_id: int):
    """Triggers scraping of a specific custom source."""
    sources = db.get_custom_sources()
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Custom source not found")

    scraper = UniversalScraper(db)
    result = scraper.scrape_source(source)
    return result


@app.post("/api/scrape/custom-all")
def scrape_all_custom_sources():
    """Triggers scraping of all active custom sources."""
    scraper = UniversalScraper(db)
    results = scraper.scrape_all_active()
    return {"success": True, "results": results}


# =============================================================================
# Milestone 15: AI Resume Matching, Grade Extractor & Dynamic Recommendations
# =============================================================================

@app.get("/api/resume/status")
def get_resume_status():
    """Returns candidate's current resume status, academic standing, and AI engine status."""
    profile = db.get_user_profile()
    settings = db.get_all_settings()
    gemini_key = settings.get("gemini_api_key")
    has_gemini = bool(gemini_key)

    return {
        "has_resume": bool(profile.get("resume_raw")),
        "full_name": profile.get("full_name"),
        "gpa_grades": profile.get("gpa_grades") or "Not Calibrated",
        "degree": profile.get("degree"),
        "experience_years": profile.get("experience_years"),
        "skills_count": len(profile.get("skills_list") or []),
        "has_gemini_key": has_gemini,
        "masked_gemini_key": f"{gemini_key[:6]}...{gemini_key[-4:]}" if has_gemini and len(gemini_key) > 10 else None,
        "active_engine": "Google Gemini Free Tier" if has_gemini else "Built-in Free Heuristic AI Engine",
    }


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Uploads a resume file (.pdf, .txt, .md), extracts text, and parses credentials via AI."""
    try:
        contents = await file.read()
        text = AIResumeService.extract_text(contents, file.filename)
        if not text.strip():
            return JSONResponse(status_code=400, content={"success": False, "error": "Could not extract text from uploaded file."})

        settings = db.get_all_settings()
        gemini_key = settings.get("gemini_api_key")

        parsed = AIResumeService.parse_resume(text, api_key=gemini_key)
        return {
            "success": True,
            "filename": file.filename,
            "extracted_profile": parsed,
            "raw_text_preview": text[:500] + ("..." if len(text) > 500 else ""),
            "raw_text": text,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/resume/parse-text")
def parse_resume_text(req: ResumeParseTextRequest):
    """Parses raw pasted resume text and returns structured candidate credentials."""
    try:
        if not req.resume_text.strip():
            return JSONResponse(status_code=400, content={"success": False, "error": "Resume text cannot be empty."})

        settings = db.get_all_settings()
        gemini_key = req.api_key or settings.get("gemini_api_key")

        parsed = AIResumeService.parse_resume(req.resume_text, api_key=gemini_key)
        return {
            "success": True,
            "extracted_profile": parsed,
            "raw_text": req.resume_text,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/resume/apply-to-profile")
def apply_resume_to_profile(req: ResumeApplyRequest):
    """Saves the extracted candidate data and raw resume text to the user's active profile."""
    try:
        updated = db.update_resume_data(
            resume_raw=req.resume_raw or "",
            extracted=req.extracted_data,
        )
        return {"success": True, "profile": updated}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/resume/recommendations")
def get_resume_recommendations(request: Request):
    """Generates dynamic AI recommendations across scholarships, jobs, and grants tailored to user's resume."""
    try:
        curr = resolve_current_user(request)
        profile = db.get_user_profile(user_id=str(curr["id"]) if curr else None, email=curr.get("email") if curr else None)
        recommendations = AIResumeService.get_dynamic_recommendations(profile, db)
        return {"success": True, **recommendations}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/settings/gemini-key")
def get_gemini_key_setting():
    """Returns whether the Google Gemini API key is configured."""
    settings = db.get_all_settings()
    key = settings.get("gemini_api_key")
    return {
        "configured": bool(key),
        "masked_key": f"{key[:6]}...{key[-4:]}" if key and len(key) > 10 else None,
    }


@app.post("/api/settings/gemini-key")
def save_gemini_key(req: GeminiKeyRequest):
    """Saves or updates the Google Gemini API key in SQLite settings."""
    try:
        clean_key = req.api_key.strip()
        db.save_setting("gemini_api_key", clean_key)
        return {"success": True, "message": "Gemini API key saved successfully."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.delete("/api/settings/gemini-key")
def clear_gemini_key():
    """Removes the stored Gemini API key to fallback to the offline AI engine."""
    with db._get_connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'gemini_api_key';")
        conn.commit()
    return {"success": True, "message": "Gemini key removed. Reverted to built-in offline AI."}
