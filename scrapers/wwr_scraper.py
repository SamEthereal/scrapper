"""WeWorkRemotely Scraper for Remote Tech Jobs & High-Ticket Gigs.

Fetches and parses public RSS feeds from WeWorkRemotely (WWR) across
programming, software engineering, and DevOps categories.
"""

import re
import xml.etree.ElementTree as ET
from typing import List, Optional
import httpx

from parsers.job_parser import JobItem, extract_salary


class WWRScraper:
    """Scrapes remote developer jobs and gigs from WeWorkRemotely RSS feeds."""

    DEFAULT_FEEDS = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.client = httpx.Client(
            headers=self.DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=self.timeout,
        )

    def scrape(self, limit: int = 50) -> List[JobItem]:
        """
        Fetches and extracts jobs from WeWorkRemotely RSS feeds.

        Args:
            limit: Maximum number of jobs to retrieve.

        Returns:
            List of parsed JobItem instances.
        """
        jobs: List[JobItem] = []
        seen_urls = set()

        for feed_url in self.DEFAULT_FEEDS:
            if len(jobs) >= limit:
                break

            try:
                response = self.client.get(feed_url)
                if response.status_code != 200:
                    continue

                root = ET.fromstring(response.text)
                channel = root.find("channel")
                if channel is None:
                    continue

                for item in channel.findall("item"):
                    if len(jobs) >= limit:
                        break

                    raw_title = (item.findtext("title") or "").strip()
                    url = (item.findtext("link") or "").strip()
                    region = (item.findtext("region") or "Anywhere in the World").strip()
                    desc = (item.findtext("description") or "")

                    if not raw_title or not url or url in seen_urls:
                        continue

                    seen_urls.add(url)

                    # WWR titles are typically "Company Name: Job Title"
                    if ":" in raw_title:
                        company_part, title_part = raw_title.split(":", 1)
                        company = company_part.strip()
                        job_title = title_part.strip()
                    else:
                        company = "Remote Tech"
                        job_title = raw_title

                    # Extract potential salary mentions in description text
                    salary = None
                    desc_clean = re.sub(r"<[^>]+>", " ", desc)
                    salary_match = re.search(r"(\$[\d,]+k?|\€[\d,]+k?|\£[\d,]+k?)\s*(?:–|-|to)\s*(\$[\d,]+k?|\€[\d,]+k?|\£[\d,]+k?)", desc_clean, re.IGNORECASE)
                    if salary_match:
                        salary = salary_match.group(0).strip()
                    elif "$" in desc_clean or "€" in desc_clean:
                        # Check single salary tokens
                        words = desc_clean.split()
                        salary = extract_salary(words)

                    jobs.append(
                        JobItem(
                            title=job_title,
                            company=company,
                            location=f"Remote ({region})",
                            is_remote=True,
                            salary=salary,
                            schedule="Remote Full-Time / Contract",
                            work_life_score=85,
                            url=url,
                            source="WeWorkRemotely",
                        )
                    )

            except Exception:
                # Silently continue to next feed if one fails
                continue

        return jobs
