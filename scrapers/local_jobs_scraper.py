"""Local Jobs Scraper (Ethiopia) — Reporter Jobs, Ethiojobs & Elelan.

Implements two-tier scraping with structured data extraction:
- Seniority extraction (Fresh Graduate / Junior, Mid-Level, Senior)
- Industry / Category classification
- Location normalization (Addis Ababa, Regional, Remote)
- Strict quality gating (discard malformed or spam listings)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

from parsers.job_parser import JobItem, extract_salary
from parsers.normalizer import (
    normalize_experience_level,
    normalize_job_category,
    normalize_job_type,
)
from storage.db import OpportunityDB

logger = logging.getLogger("local_jobs_scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class LocalJobsScraper:
    """Scrapes structured Ethiopian local jobs with strict quality filtering."""

    def __init__(self, db: OpportunityDB):
        self.db = db

    # =========================================================================
    # 1. Ethiopian Reporter Jobs
    # =========================================================================
    def scrape_reporter_jobs(
        self,
        category_url: Optional[str] = None,
        limit: int = 15,
    ) -> Dict[str, Any]:
        """
        Scrapes Ethiopian Reporter Jobs with structured career-level and industry tags.
        Default targets ICT/Telecommunications & Professional roles.
        """
        url = category_url or (
            "https://www.ethiopianreporterjobs.com/jobs-in-ethiopia/?"
            "industry=ict-telecommunication&location_location1=Ethiopia"
        )
        source_name = "Reporter Jobs"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    logger.warning("Reporter jobs returned HTTP %d", resp.status_code)
                    # Fallback to ethiojobs if reporter jobs is unreachable or blocked
                    return self.scrape_ethiojobs(limit=limit)

                soup = BeautifulSoup(resp.text, "html.parser")

            cards = (
                soup.find_all("div", class_=lambda c: c and "job-listing" in c)
                or soup.find_all("article", class_=lambda c: c and "job" in c)
                or soup.find_all("div", class_=lambda c: c and ("card" in c or "listing" in c or "loop" in c))
            )

            if not cards:
                cards = soup.find_all("a", href=lambda h: h and "/job/" in h)

            for card in cards[:limit]:
                title = ""
                detail_url = ""
                company = "Various Employers"
                location = "Addis Ababa, Ethiopia"
                card_text = card.get_text(separator=" ", strip=True)

                if card.name == "a":
                    title = card_text
                    detail_url = urljoin(url, card.get("href", ""))
                else:
                    a_tag = card.find("a", href=lambda h: h and "/job/" in h) or card.find("a")
                    if a_tag:
                        title = a_tag.get_text(strip=True)
                        detail_url = urljoin(url, a_tag.get("href", ""))

                if not title or len(title) < 5 or not detail_url:
                    continue

                comp_tag = card.find(class_=lambda c: c and ("company" in c or "employer" in c or "author" in c))
                if comp_tag:
                    company = comp_tag.get_text(strip=True)

                loc_tag = card.find(class_=lambda c: c and ("location" in c or "city" in c))
                if loc_tag:
                    location = loc_tag.get_text(strip=True)

                exp_level = normalize_experience_level(title, card_text)
                category = normalize_job_category(title, card_text)
                job_type = normalize_job_type(title, card_text, is_remote="remote" in location.lower())

                job = JobItem(
                    title=title,
                    company=company,
                    location=location,
                    is_remote="remote" in location.lower(),
                    salary=extract_salary(card_text.split()),
                    schedule=None,
                    work_life_score=75,
                    url=detail_url,
                    source=source_name,
                    experience_level=exp_level,
                    category=category,
                    job_type=job_type,
                )

                if self.db.save_job(job):
                    new_count += 1
                scraped += 1

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.warning("Error scraping Reporter Jobs (%s), falling back to Ethiojobs...", e)
            return self.scrape_ethiojobs(limit=limit)

    # =========================================================================
    # 2. Ethiojobs (Ethiopia's Premier Career Portal)
    # =========================================================================
    def scrape_ethiojobs(
        self,
        category_url: Optional[str] = None,
        limit: int = 15,
    ) -> Dict[str, Any]:
        """
        Scrapes Ethiojobs (https://www.ethiojobs.net/jobs).
        Parses structured title, employer, experience, and deadlines.
        """
        url = category_url or "https://www.ethiojobs.net/browse-by-category/information-technology/"
        source_name = "Ethiojobs"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get("https://ethiojobs.net/jobs")
                if resp.status_code != 200:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                # Strategy 1: Check for embedded __NEXT_DATA__ JSON
                next_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', resp.text)
                if next_match:
                    try:
                        next_json = json.loads(next_match.group(1))
                        jobs_val = next_json.get("props", {}).get("pageProps", {}).get("jobs", {})
                        job_list = jobs_val.get("data", []) if isinstance(jobs_val, dict) else (jobs_val if isinstance(jobs_val, list) else [])
                        if job_list:
                            for item in job_list[:limit]:
                                title = (item.get("title") or "").strip()
                                if not title or len(title) < 4:
                                    continue
                                slug = item.get("slug") or ""
                                detail_url = f"https://ethiojobs.net/jobs/{slug}" if slug else "https://ethiojobs.net/jobs"
                                comp_obj = item.get("company")
                                comp_name = comp_obj.get("name") if isinstance(comp_obj, dict) else "Ethiopian Employer"
                                state = item.get("state") or "Addis Ababa"
                                location = f"{state}, Ethiopia"
                                loc_type = str(item.get("location_type") or "").lower()
                                is_remote = "remote" in loc_type or "remote" in title.lower()

                                cats = item.get("catalogs") or []
                                cat_str = cats[0].get("name") if (cats and isinstance(cats[0], dict)) else ""
                                category = normalize_job_category(title, cat_str)
                                exp_level = normalize_experience_level(title, cat_str)
                                job_type = "Full-time"

                                job = JobItem(
                                    title=title,
                                    company=comp_name,
                                    location=location,
                                    is_remote=is_remote,
                                    salary="",
                                    schedule="Full-time",
                                    work_life_score=75,
                                    url=detail_url,
                                    source=source_name,
                                    experience_level=exp_level,
                                    category=category,
                                    job_type=job_type,
                                )
                                if self.db.save_job(job):
                                    new_count += 1
                                scraped += 1

                            if scraped > 0:
                                return {"success": True, "scraped": scraped, "new": new_count, "error": None}
                    except Exception as e:
                        logger.warning(f"Failed parsing Ethiojobs __NEXT_DATA__: {e}")

                soup = BeautifulSoup(resp.text, "html.parser")

            cards = (
                soup.find_all("div", class_=lambda c: c and ("listing" in c or "job-item" in c or "single-job" in c))
                or soup.find_all("div", id=lambda i: i and "job" in i)
                or soup.find_all("article")
            )

            if not cards:
                cards = soup.find_all("a", href=lambda h: h and ("/display-job/" in h or "/jobs/" in h))

            for card in cards[:limit]:
                title = ""
                detail_url = ""
                company = "Ethiopian Employer"
                location = "Addis Ababa, Ethiopia"
                card_text = card.get_text(separator=" ", strip=True)

                if card.name == "a":
                    title = card_text
                    detail_url = urljoin(url, card.get("href", ""))
                else:
                    a_tag = card.find("a", href=lambda h: h and ("/display-job/" in h or "/job/" in h)) or card.find("a", href=True)
                    if a_tag:
                        title = a_tag.get_text(strip=True)
                        detail_url = urljoin(url, a_tag.get("href", ""))

                if not title or len(title) < 5 or not detail_url:
                    continue

                comp_tag = card.find(class_=lambda c: c and ("company" in c or "employer" in c))
                if comp_tag:
                    company = comp_tag.get_text(strip=True)

                loc_tag = card.find(class_=lambda c: c and ("location" in c or "city" in c))
                if loc_tag:
                    location = loc_tag.get_text(strip=True)

                exp_level = normalize_experience_level(title, card_text)
                category = normalize_job_category(title, card_text)
                job_type = normalize_job_type(title, card_text, is_remote="remote" in location.lower())

                job = JobItem(
                    title=title,
                    company=company,
                    location=location,
                    is_remote="remote" in location.lower(),
                    salary=extract_salary(card_text.split()),
                    schedule=None,
                    work_life_score=75,
                    url=detail_url,
                    source=source_name,
                    experience_level=exp_level,
                    category=category,
                    job_type=job_type,
                )

                if self.db.save_job(job):
                    new_count += 1
                scraped += 1

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping Ethiojobs: %s", e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}

    # =========================================================================
    # 2. Elelan Jobs (Two-Tier Crawler)
    # =========================================================================
    def scrape_elelan_jobs(self, limit: int = 10) -> Dict[str, Any]:
        """
        Two-tier crawler for Elelan Jobs:
        - Tier 1: Extracts job post URLs from homepage/archive.
        - Tier 2: Visits detail URL to extract company, requirements, and deadline.
        """
        base_url = "https://elelanjobs.com/"
        source_name = "Elelan Jobs"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(base_url)
                if resp.status_code != 200:
                    return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                soup = BeautifulSoup(resp.text, "html.parser")

                # Find job post links
                links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/job/" in href and href not in links:
                        links.append(href)

                # Tier 2: Visit each detail link (up to limit)
                for detail_url in links[:limit]:
                    try:
                        detail_resp = client.get(detail_url)
                        if detail_resp.status_code != 200:
                            continue

                        detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                        h1 = detail_soup.find("h1")
                        title = h1.get_text(strip=True) if h1 else ""

                        if not title:
                            continue

                        body_text = detail_soup.get_text(separator=" ", strip=True)

                        # Extract company name from meta or title
                        company = "Ethiopian Employer"
                        comp_match = re.search(r"Company:\s*([^\n\r,]+)", body_text, re.IGNORECASE)
                        if comp_match:
                            company = comp_match.group(1).strip()

                        # Extract location
                        location = "Addis Ababa, Ethiopia"
                        if "remote" in body_text.lower():
                            location = "Remote / Ethiopia"

                        exp_level = normalize_experience_level(title, body_text)
                        category = normalize_job_category(title, body_text)
                        job_type = normalize_job_type(title, body_text)

                        job = JobItem(
                            title=title,
                            company=company,
                            location=location,
                            is_remote="remote" in location.lower(),
                            salary=extract_salary(body_text.split()),
                            schedule=None,
                            work_life_score=70,
                            url=detail_url,
                            source=source_name,
                            experience_level=exp_level,
                            category=category,
                            job_type=job_type,
                        )

                        if self.db.save_job(job):
                            new_count += 1
                        scraped += 1

                    except Exception as inner_e:
                        logger.debug("Failed Tier 2 Elelan crawl %s: %s", detail_url, inner_e)
                        continue

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping Elelan Jobs: %s", e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}

    # =========================================================================
    # 3. RemoteOK API (Foreign Tech & Junior/Senior Jobs)
    # =========================================================================
    def scrape_remoteok(self, limit: int = 20) -> Dict[str, Any]:
        """
        Scrapes RemoteOK API with structured tags and seniority levels.
        High-paying global remote software engineering & IT jobs.
        """
        url = "https://remoteok.com/api"
        source_name = "RemoteOK"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                data = resp.json()

            # First item is metadata disclaimer
            postings = [p for p in data if isinstance(p, dict) and p.get("position")]

            for post in postings[:limit]:
                title = post.get("position", "")
                company = post.get("company", "Global Tech Company")
                job_url = post.get("url") or f"https://remoteok.com/l/{post.get('id', '')}"
                description = post.get("description", "")
                tags = " ".join(post.get("tags", []))
                context = f"{tags} {description[:300]}"

                salary = None
                salary_min = post.get("salary_min")
                salary_max = post.get("salary_max")
                if salary_min and salary_max:
                    salary = f"${int(salary_min):,} – ${int(salary_max):,} USD"

                exp_level = normalize_experience_level(title, context)
                category = normalize_job_category(title, context)
                job_type = normalize_job_type(title, context, is_remote=True)

                job = JobItem(
                    title=title,
                    company=company,
                    location="Global Remote",
                    is_remote=True,
                    salary=salary,
                    schedule=None,
                    work_life_score=85,
                    url=job_url,
                    source=source_name,
                    experience_level=exp_level,
                    category=category,
                    job_type=job_type,
                )

                if self.db.save_job(job):
                    new_count += 1
                scraped += 1

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping RemoteOK: %s", e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}
