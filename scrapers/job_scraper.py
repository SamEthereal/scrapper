"""Job scraper for online job boards (starting with 4dayweek.io)."""

from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from parsers.job_parser import JobItem, parse_job_card


class JobScraper:
    """Scrapes job boards and career sites for open job listings."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self.client = httpx.Client(
            headers=self.DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=self.timeout,
        )

    def scrape_4dayweek(self, limit: int = 50) -> List[JobItem]:
        """
        Scrapes remote jobs from https://4dayweek.io/remote-jobs.
        
        Args:
            limit: Maximum number of job listings to retrieve.
            
        Returns:
            List of parsed JobItem objects.
        """
        url = "https://4dayweek.io/remote-jobs"
        response = self.client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        card_elements = soup.find_all("div", attrs={"data-testid": "job-card"})

        jobs: List[JobItem] = []
        for card in card_elements[:limit]:
            item = parse_job_card(card, base_url="https://4dayweek.io")
            if item:
                jobs.append(item)

        return jobs
