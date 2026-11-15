"""OHUB Opportunities Web Scraper (Direct API Engine).

Integrates with OHUB's backend API: https://api.ohubet.com/scholarships
Categories:
- Scholarships: categoryId=3de2504f-4ab1-4cf2-a6d8-3b1448db7b3d
- Fellowships: categoryId=0d1ec0e9-d25d-41ae-a6ea-336acfe2c318
- Internships: categoryId=b18109d5-3b49-497f-bac0-36049f852a30
- Jobs: categoryId=23619046-7ac0-40bd-b6c3-78eb5adcd7b7

Extracts clean structured titles, deadlines, countries, degree levels, and direct
official application portals, routing scholarships/fellowships to `opportunities`
and jobs/internships to `jobs` table with automated multi-tier deduplication.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx

from parsers.scholarship_parser import OpportunityItem, normalize_deadline
from parsers.job_parser import JobItem, extract_salary
from parsers.normalizer import (
    normalize_country,
    normalize_academic_level,
    normalize_funding_type,
    normalize_experience_level,
    normalize_job_category,
    normalize_job_type,
)
from storage.db import OpportunityDB

logger = logging.getLogger("ohub_web_scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

API_BASE_URL = "https://api.ohubet.com"
PORTAL_BASE_URL = "https://opportunities.ohubet.com"

CATEGORIES = {
    "scholarships": {
        "category_id": "3de2504f-4ab1-4cf2-a6d8-3b1448db7b3d",
        "target": "opportunity",
        "default_level": "Master's",
    },
    "fellowships": {
        "category_id": "0d1ec0e9-d25d-41ae-a6ea-336acfe2c318",
        "target": "opportunity",
        "default_level": "Fellowship / Postdoc",
    },
    "internships": {
        "category_id": "b18109d5-3b49-497f-bac0-36049f852a30",
        "target": "job",
        "default_type": "Internship",
        "default_exp": "Junior / Entry",
    },
    "jobs": {
        "category_id": "23619046-7ac0-40bd-b6c3-78eb5adcd7b7",
        "target": "job",
        "default_type": "Full-time",
        "default_exp": "Mid-Level",
    },
}


def _safe_str(val: Any) -> str:
    """Safely converts string, dict, or list into a clean string without throwing."""
    if not val:
        return ""
    if isinstance(val, dict):
        return str(val.get("name") or val.get("title") or val.get("label") or "").strip()
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x).strip()
    return str(val).strip()


class OHUBWebScraper:
    """Scrapes OHUB platform opportunities with clean routing & deduplication."""

    def __init__(self, db: OpportunityDB):
        self.db = db

    def scrape_category(self, category_key: str = "scholarships", limit: int = 20) -> Dict[str, Any]:
        """Scrapes a specific category from OHUB API."""
        config = CATEGORIES.get(category_key.lower())
        if not config:
            return {"success": False, "error": f"Unknown category: {category_key}", "scraped": 0, "new": 0}

        category_id = config["category_id"]
        target = config["target"]
        scraped = 0
        new_count = 0

        api_url = f"{API_BASE_URL}/scholarships?categoryId={category_id}&limit={limit}"

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(api_url)
                if resp.status_code != 200:
                    return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                payload = resp.json()
                items = payload.get("data", []) if isinstance(payload, dict) else []

                for item in items:
                    title = _safe_str(item.get("title"))
                    if not title or len(title) < 5:
                        continue

                    slug = _safe_str(item.get("slug")) or _safe_str(item.get("id"))
                    detail_url = f"{PORTAL_BASE_URL}/opportunities/{slug}"
                    application_url = _safe_str(item.get("applicationUrl"))
                    official_portal = application_url if application_url.startswith("http") else detail_url

                    deadline_str = _safe_str(item.get("deadline"))
                    deadline_date = normalize_deadline(deadline_str) if deadline_str else None

                    summary_html = item.get("summary") or ""
                    clean_summary = BeautifulSoup(summary_html, "html.parser").get_text(separator=" ", strip=True)

                    host_inst = _safe_str(item.get("hostInstitution"))
                    org_name = host_inst if host_inst else "OHUB Opportunities"
                    location = _safe_str(item.get("hostLocationOverride")) or _safe_str(item.get("hostCountry")) or "Global / Remote"

                    # Benefits highlights
                    highlights = []
                    if item.get("coversTuition"):
                        highlights.append("100% Tuition Fee Covered")
                    if item.get("coversLiving"):
                        highlights.append("Living Allowance / Stipend Included")
                    if item.get("coversFlight"):
                        highlights.append("Round-Trip Travel Flights Included")
                    if item.get("extraBenefits"):
                        highlights.append(str(item.get("extraBenefits"))[:80])

                    if not highlights and clean_summary:
                        highlights.append(clean_summary[:120] + "...")

                    scraped += 1

                    if target == "opportunity":
                        country = _safe_str(item.get("hostCountry")) or normalize_country(title, clean_summary)
                        degree_arr = item.get("degreeLevel") or []
                        if degree_arr and isinstance(degree_arr, list) and degree_arr[0] != "ANY":
                            level = normalize_academic_level(" ".join(str(x) for x in degree_arr), clean_summary)
                        else:
                            level = normalize_academic_level(title, clean_summary)

                        if level == "All Levels" and "default_level" in config:
                            level = config["default_level"]

                        raw_funding = _safe_str(item.get("fundingType"))
                        if "FULL" in raw_funding.upper():
                            funding = "100% Fully Funded"
                        else:
                            funding = normalize_funding_type(title, clean_summary)

                        post_id_val = f"ohub_{_safe_str(item.get('id', slug))[:10]}"
                        pub_date = _safe_str(item.get("publishedAt"))[:10]

                        opp = OpportunityItem(
                            post_id=post_id_val,
                            channel_name="OHUB Opportunities",
                            post_url=detail_url,
                            date=pub_date,
                            title=title,
                            deadline=deadline_str or "",
                            deadline_date=deadline_date,
                            apply_url=detail_url,
                            is_opportunity=True,
                            raw_text=clean_summary or title,
                            country=country or "Global",
                            academic_level=level or "All Levels",
                            funding_type=funding or "Fully Funded",
                        )

                        if self.db.save_opportunity(opp, official_portal=official_portal, key_highlights=highlights):
                            new_count += 1

                    elif target == "job":
                        job_type = normalize_job_type(title, clean_summary)
                        if "default_type" in config and job_type == "Full-time":
                            job_type = config["default_type"]

                        exp_level = normalize_experience_level(title, clean_summary)
                        if "default_exp" in config and exp_level == "Mid-Level":
                            exp_level = config["default_exp"]

                        category = normalize_job_category(title, clean_summary)
                        salary_str = extract_salary([clean_summary]) or ""

                        is_remote = (
                            "remote" in location.lower()
                            or "worldwide" in location.lower()
                            or "remote" in title.lower()
                        )

                        job = JobItem(
                            title=title,
                            company=org_name,
                            location=location,
                            is_remote=is_remote,
                            salary=salary_str or "",
                            schedule=job_type,
                            url=official_portal or detail_url,
                            source="OHUB Opportunities",
                            experience_level=exp_level,
                            category=category,
                            job_type=job_type,
                        )
                        if self.db.save_job(job):
                            new_count += 1

        except Exception as e:
            logger.error(f"Error scraping OHUB category {category_key}: {e}", exc_info=True)
            return {"success": False, "scraped": scraped, "new": new_count, "error": str(e)}

        return {"success": True, "scraped": scraped, "new": new_count, "error": None}

    def scrape_all_categories(self, limit_per_cat: int = 8) -> Dict[str, Any]:
        """Alias for scrape_all matching FastAPI router call."""
        return self.scrape_all(limit_per_category=limit_per_cat)

    def scrape_all(self, limit_per_category: int = 15) -> Dict[str, Any]:
        """Scrapes all 4 major OHUB categories."""
        results = {}
        total_scraped = 0
        total_new = 0

        for cat in CATEGORIES.keys():
            res = self.scrape_category(cat, limit=limit_per_category)
            results[cat] = res
            total_scraped += res.get("scraped", 0)
            total_new += res.get("new", 0)

        return {
            "success": True,
            "total_scraped": total_scraped,
            "total_new": total_new,
            "categories": results,
        }
