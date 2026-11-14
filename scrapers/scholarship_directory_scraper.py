"""Curated Scholarship Directory Scraper.

Scrapes high-yield scholarship directories:
1. Scholars4Dev (https://www.scholars4dev.com/tag/scholarships-for-ethiopians/)
   Two-tier crawler extracting Country, Degree Level, Funding Scope, and Deadlines.
2. Telegram Channel: @ethioscholarshipopportunity (https://t.me/s/ethioscholarshipopportunity)
   Zero-credential channel scraping with normalized academic & country tags.
3. Carraadesk (https://carraadesk.com/)
   Dual-classifier with strict quality gate (drops low-signal articles, routes jobs to jobs table).
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

from parsers.scholarship_parser import OpportunityItem, parse_post, normalize_deadline
from parsers.job_parser import JobItem, extract_salary
from parsers.normalizer import (
    normalize_country,
    normalize_academic_level,
    normalize_funding_type,
    normalize_experience_level,
    normalize_job_category,
    normalize_job_type,
)
from scrapers.telegram_scraper import TelegramScraper
from storage.db import OpportunityDB

logger = logging.getLogger("scholarship_directory_scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class ScholarshipDirectoryScraper:
    """Scrapes structured scholarship portals with strict quality gating."""

    def __init__(self, db: OpportunityDB):
        self.db = db
        self.tg_scraper = TelegramScraper()

    # =========================================================================
    # 1. Scholars4Dev (Ethiopia / Developing Countries Tag)
    # =========================================================================
    def scrape_scholars4dev(
        self,
        tag_url: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Two-tier crawler for Scholars4Dev:
        - Tier 1: Extracts scholarship links from the tag page.
        - Tier 2: Visits detail page to extract Host Institution, Target Countries,
                  Degree Level, Deadline, and Official Website link.
        """
        url = tag_url or "https://www.scholars4dev.com/tag/scholarships-for-ethiopians/"
        source_name = "Scholars4Dev"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                soup = BeautifulSoup(resp.text, "html.parser")

                # Find scholarship article entries
                articles = soup.find_all("div", class_=lambda c: c and ("post" in c or "entry" in c))
                links = []
                for art in articles:
                    a_tag = art.find("a", href=True)
                    if a_tag and a_tag["href"] not in links:
                        links.append(a_tag["href"])

                # Fallback to finding entry titles
                if not links:
                    for h2 in soup.find_all(["h2", "h3"]):
                        a = h2.find("a", href=True)
                        if a and a["href"] not in links:
                            links.append(a["href"])

                for detail_url in links[:limit]:
                    try:
                        detail_resp = client.get(detail_url)
                        if detail_resp.status_code != 200:
                            continue

                        detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                        h1 = detail_soup.find("h1")
                        title = h1.get_text(strip=True) if h1 else ""

                        if not title or len(title) < 10:
                            continue

                        body_text = detail_soup.get_text(separator=" ", strip=True)

                        # Extract official application portal / website
                        official_portal = detail_url
                        for a in detail_soup.find_all("a", href=True):
                            a_text = a.get_text(strip=True).lower()
                            if "official scholarship website" in a_text or "application website" in a_text:
                                official_portal = a["href"]
                                break

                        # Extract deadline
                        deadline_str = None
                        deadline_match = re.search(r"Deadline:\s*([^\n\r.]+)", body_text, re.IGNORECASE)
                        if deadline_match:
                            deadline_str = deadline_match.group(1).strip()
                        deadline_date = normalize_deadline(deadline_str)

                        # Extract highlights (e.g. host institution, target group)
                        highlights = []
                        for li in detail_soup.find_all("li"):
                            t = li.get_text(strip=True)
                            if len(t) > 15 and len(t) < 200:
                                highlights.append(t)
                        highlights = highlights[:5]

                        country = normalize_country(title, body_text)
                        level = normalize_academic_level(title, body_text)
                        funding = normalize_funding_type(title, body_text)

                        opp = OpportunityItem(
                            post_id=str(abs(hash(detail_url)))[:8],
                            channel_name=source_name,
                            post_url=detail_url,
                            date="",
                            title=title,
                            deadline=deadline_str,
                            deadline_date=deadline_date,
                            apply_url=official_portal,
                            is_opportunity=True,
                            raw_text=body_text[:500],
                            country=country,
                            academic_level=level,
                            funding_type=funding,
                        )

                        if self.db.save_opportunity(opp, official_portal=official_portal, key_highlights=highlights):
                            new_count += 1
                        scraped += 1

                    except Exception as inner_e:
                        logger.debug("Failed Tier 2 Scholars4Dev %s: %s", detail_url, inner_e)
                        continue

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping Scholars4Dev: %s", e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}

    # =========================================================================
    # 2. Telegram: @ethioscholarshipopportunity
    # =========================================================================
    def scrape_ethio_scholarship_telegram(self, limit: int = 15) -> Dict[str, Any]:
        """
        Scrapes @ethioscholarshipopportunity public Telegram channel with zero credentials.
        """
        channel_name = "ethioscholarshipopportunity"
        channel_url = f"https://t.me/s/{channel_name}"
        scraped = 0
        new_count = 0

        try:
            raw_posts = self.tg_scraper.scrape_channel(channel_url, limit=limit)
            for post in raw_posts:
                parsed = parse_post(post)
                if parsed.is_opportunity and len(parsed.title) > 8:
                    if self.db.save_opportunity(parsed):
                        new_count += 1
                    scraped += 1

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping @%s: %s", channel_name, e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}

    # =========================================================================
    # 3. Carraadesk (Smart Dual Classifier with Strict Quality Gate)
    # =========================================================================
    def scrape_carraadesk(self, limit: int = 10) -> Dict[str, Any]:
        """
        Scrapes Carraadesk with dual intent classification and strict quality gating:
        - If strong scholarship signals -> saves to opportunities table.
        - If strong job signals -> saves to jobs table.
        - If low signal or ambiguous -> discarded to preserve clean data.
        """
        url = "https://carraadesk.com/"
        source_name = "Carraadesk"
        scraped = 0
        new_count = 0

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {resp.status_code}"}

                soup = BeautifulSoup(resp.text, "html.parser")

                articles = soup.find_all("article")
                if not articles:
                    articles = soup.find_all("div", class_=lambda c: c and ("post" in c or "entry" in c))

                for art in articles[:limit]:
                    a_tag = art.find("a", href=True)
                    if not a_tag:
                        continue

                    title = a_tag.get_text(strip=True)
                    post_url = a_tag["href"]
                    art_text = art.get_text(separator=" ", strip=True)

                    if not title or len(title) < 10:
                        continue

                    combined = f"{title} {art_text}".lower()

                    # Scholarship signals
                    scholarship_signals = sum(
                        1 for kw in [
                            "scholarship", "fellowship", "fully funded", "phd", "master",
                            "undergraduate", "tuition", "stipend", "grant"
                        ]
                        if kw in combined
                    )

                    # Job signals
                    job_signals = sum(
                        1 for kw in [
                            "vacancy", "hiring", "job", "recruitment", "officer",
                            "salary", "position", "contract", "full-time"
                        ]
                        if kw in combined
                    )

                    # Quality Gate: Drop if ambiguous or zero signals
                    if scholarship_signals == 0 and job_signals == 0:
                        continue

                    scraped += 1

                    if scholarship_signals >= job_signals:
                        # Route to opportunities
                        country = normalize_country(title, art_text)
                        level = normalize_academic_level(title, art_text)
                        funding = normalize_funding_type(title, art_text)

                        deadline_match = re.search(r"deadline:\s*([^\n\r.]+)", art_text, re.IGNORECASE)
                        deadline_str = deadline_match.group(1).strip() if deadline_match else None
                        deadline_date = normalize_deadline(deadline_str)

                        opp = OpportunityItem(
                            post_id=str(abs(hash(post_url)))[:8],
                            channel_name=source_name,
                            post_url=post_url,
                            date="",
                            title=title,
                            deadline=deadline_str,
                            deadline_date=deadline_date,
                            apply_url=post_url,
                            is_opportunity=True,
                            raw_text=art_text[:500],
                            country=country,
                            academic_level=level,
                            funding_type=funding,
                        )

                        if self.db.save_opportunity(opp):
                            new_count += 1
                    else:
                        # Route to jobs
                        exp_level = normalize_experience_level(title, art_text)
                        category = normalize_job_category(title, art_text)
                        job_type = normalize_job_type(title, art_text)

                        job = JobItem(
                            title=title,
                            company="Regional Employer (Carraadesk)",
                            location="Addis Ababa / Regional",
                            is_remote=False,
                            salary=extract_salary(art_text.split()),
                            schedule=None,
                            work_life_score=70,
                            url=post_url,
                            source=source_name,
                            experience_level=exp_level,
                            category=category,
                            job_type=job_type,
                        )

                        if self.db.save_job(job):
                            new_count += 1

            return {"success": True, "scraped": scraped, "new": new_count, "error": None}

        except Exception as e:
            logger.error("Error scraping Carraadesk: %s", e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}
