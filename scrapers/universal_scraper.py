"""Universal Feed Scraper — Milestone 14.

Scrapes user-defined custom sources (RSS feeds, Telegram channels, and web pages)
and ingests results into the appropriate database tables based on category mapping.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

from parsers.job_parser import JobItem, extract_salary
from parsers.scholarship_parser import parse_post
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from storage.db import OpportunityDB

logger = logging.getLogger("universal_scraper")


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
}


class UniversalScraper:
    """Scrapes custom user-defined sources (RSS, Telegram, Web) and ingests results."""

    def __init__(self, db: OpportunityDB):
        self.db = db

    def scrape_source(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scrapes a single custom source and stores results.

        Args:
            source: Dict with keys id, name, url, source_type, category.

        Returns:
            Dict with success, scraped, new, error.
        """
        source_type = source.get("source_type", "rss")
        try:
            if source_type == "rss":
                result = self._scrape_rss(source)
            elif source_type == "telegram":
                result = self._scrape_telegram(source)
            elif source_type == "web":
                result = self._scrape_web(source)
            else:
                return {"success": False, "scraped": 0, "new": 0, "error": f"Unknown source type: {source_type}"}

            # Update source stats in database
            self.db.update_custom_source_stats(
                source_id=source["id"],
                items_count=result.get("scraped", 0),
            )
            return result

        except Exception as e:
            logger.error("Failed to scrape source %s: %s", source.get("name"), e)
            return {"success": False, "scraped": 0, "new": 0, "error": str(e)}

    def scrape_all_active(self) -> List[Dict[str, Any]]:
        """Scrapes all active custom sources and returns results per source."""
        sources = self.db.get_custom_sources(active_only=True)
        results = []
        for source in sources:
            result = self.scrape_source(source)
            result["source_name"] = source.get("name", "Unknown")
            result["source_id"] = source.get("id")
            results.append(result)
        return results

    # =========================================================================
    # RSS / Atom Feed Scraper
    # =========================================================================

    def _scrape_rss(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Parses an RSS/Atom feed and ingests items based on category."""
        url = source["url"]
        category = source.get("category", "jobs")
        source_name = source.get("name", "Custom RSS")

        with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=20.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                return {"success": False, "scraped": 0, "new": 0, "error": f"HTTP {response.status_code}"}

        root = ET.fromstring(response.text)

        # Support both RSS 2.0 (<channel><item>) and Atom (<entry>)
        items = []
        channel = root.find("channel")
        if channel is not None:
            items = channel.findall("item")
        else:
            # Atom feed: entries at root level
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall("atom:entry", ns) or root.findall("entry")

        scraped = 0
        new_count = 0

        for item in items[:50]:
            raw_title = (
                item.findtext("title")
                or item.findtext("{http://www.w3.org/2005/Atom}title")
                or ""
            ).strip()
            link = (
                item.findtext("link")
                or item.findtext("{http://www.w3.org/2005/Atom}link")
                or ""
            ).strip()
            # Atom links may use href attribute
            if not link:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.get("href", "")

            desc = (
                item.findtext("description")
                or item.findtext("{http://www.w3.org/2005/Atom}summary")
                or ""
            )

            if not raw_title or not link:
                continue

            scraped += 1
            is_new = self._ingest_rss_item(raw_title, link, desc, category, source_name)
            if is_new:
                new_count += 1

        return {"success": True, "scraped": scraped, "new": new_count, "error": None}

    def _ingest_rss_item(
        self, title: str, url: str, description: str, category: str, source_name: str
    ) -> bool:
        """Routes an RSS item into the correct database table based on category."""
        desc_clean = re.sub(r"<[^>]+>", " ", description)

        if category == "jobs":
            # Parse company from "Company: Title" pattern
            if ":" in title:
                company, job_title = title.split(":", 1)
                company = company.strip()
                job_title = job_title.strip()
            else:
                company = source_name
                job_title = title

            salary = None
            salary_match = re.search(
                r"(\$[\d,]+k?|€[\d,]+k?|£[\d,]+k?)\s*(?:–|-|to)\s*(\$[\d,]+k?|€[\d,]+k?|£[\d,]+k?)",
                desc_clean,
                re.IGNORECASE,
            )
            if salary_match:
                salary = salary_match.group(0).strip()
            elif "$" in desc_clean or "€" in desc_clean:
                words = desc_clean.split()
                salary = extract_salary(words)

            job = JobItem(
                title=job_title,
                company=company,
                location="Remote",
                is_remote=True,
                salary=salary,
                schedule=None,
                work_life_score=None,
                url=url,
                source=source_name,
            )
            return self.db.save_job(job)

        elif category == "scholarships":
            from parsers.scholarship_parser import OpportunityItem
            opp = OpportunityItem(
                post_id=str(hash(url))[-8:],
                channel_name=source_name,
                post_url=url,
                date="",
                title=title,
                deadline=None,
                deadline_date=None,
                apply_url=url,
                is_opportunity=True,
            )
            return self.db.save_opportunity(opp)

        elif category == "grants":
            grant = {
                "title": title,
                "organization": source_name,
                "funding_amount": None,
                "deadline": None,
                "deadline_date": None,
                "location": "Global / Remote",
                "stage": "Open",
                "url": url,
                "key_highlights": [desc_clean[:200]] if desc_clean.strip() else [],
                "source": source_name,
            }
            return self.db.save_grant(grant)

        return False

    # =========================================================================
    # Telegram Channel Scraper
    # =========================================================================

    def _scrape_telegram(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Scrapes a Telegram public channel and ingests posts based on category."""
        url = source["url"]
        category = source.get("category", "scholarships")

        tg_scraper = TelegramScraper()
        raw_posts = tg_scraper.scrape_channel(url, limit=10)

        scraped = 0
        new_count = 0

        for post in raw_posts:
            parsed = parse_post(post)
            scraped += 1

            if category == "scholarships":
                is_new = self.db.save_opportunity(parsed)
            elif category == "jobs":
                job = JobItem(
                    title=parsed.title,
                    company=parsed.channel_name,
                    location="Remote",
                    is_remote=True,
                    salary=None,
                    schedule=None,
                    work_life_score=None,
                    url=parsed.apply_url or parsed.post_url or "",
                    source=f"Telegram @{parsed.channel_name}",
                )
                is_new = self.db.save_job(job)
            elif category == "grants":
                grant = {
                    "title": parsed.title,
                    "organization": f"Telegram @{parsed.channel_name}",
                    "funding_amount": None,
                    "deadline": parsed.deadline,
                    "deadline_date": parsed.deadline_date,
                    "location": "Global / Remote",
                    "stage": "Open",
                    "url": parsed.apply_url or parsed.post_url or "",
                    "key_highlights": [],
                    "source": f"Telegram @{parsed.channel_name}",
                }
                is_new = self.db.save_grant(grant)
            else:
                is_new = False

            if is_new:
                new_count += 1

        return {"success": True, "scraped": scraped, "new": new_count, "error": None}

    # =========================================================================
    # General Web Page Scraper
    # =========================================================================

    def _scrape_web(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Scrapes a web page for content and ingests as a single listing."""
        url = source["url"]
        category = source.get("category", "scholarships")
        source_name = source.get("name", "Custom Web Source")

        web_scraper = WebScraper()
        page_data = web_scraper.scrape(url)

        new_count = 0
        title = page_data.title or source_name
        portal = page_data.apply_links[0] if page_data.apply_links else url
        highlights = page_data.key_highlights or []

        if category == "scholarships":
            from parsers.scholarship_parser import OpportunityItem
            opp = OpportunityItem(
                post_id=str(hash(url))[-8:],
                channel_name=source_name,
                post_url=url,
                date="",
                title=title,
                deadline=None,
                deadline_date=None,
                apply_url=portal,
                is_opportunity=True,
            )
            is_new = self.db.save_opportunity(opp, official_portal=portal, key_highlights=highlights)
        elif category == "jobs":
            job = JobItem(
                title=title,
                company=source_name,
                location="Remote",
                is_remote=True,
                salary=None,
                schedule=None,
                work_life_score=None,
                url=portal,
                source=source_name,
            )
            is_new = self.db.save_job(job)
        elif category == "grants":
            grant = {
                "title": title,
                "organization": source_name,
                "funding_amount": None,
                "deadline": None,
                "deadline_date": None,
                "location": "Global / Remote",
                "stage": "Open",
                "url": portal,
                "key_highlights": highlights,
                "source": source_name,
            }
            is_new = self.db.save_grant(grant)
        else:
            is_new = False

        if is_new:
            new_count = 1

        return {"success": True, "scraped": 1, "new": new_count, "error": None}
