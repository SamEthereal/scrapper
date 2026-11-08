"""General Web Scraper for Opportunity and Job Websites.

Fetches web pages, strips boilerplate (nav, footer, ads),
extracts semantic metadata (title, headings, text), and locates
action links (Apply, Register, Official Portal).
"""

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class ScrapedWebPage:
    """Represents structured content extracted from a webpage."""
    url: str
    title: str
    meta_description: Optional[str] = None
    main_heading: str = ""
    summary_paragraphs: List[str] = field(default_factory=list)
    key_highlights: List[str] = field(default_factory=list)
    apply_links: List[str] = field(default_factory=list)


class WebScraper:
    """Scrapes and extracts key content and application links from generic web pages."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # HTML tags that usually contain navigation, scripts, or non-content clutter
    BOILERPLATE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.client = httpx.Client(
            headers=self.DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=self.timeout
        )

    def fetch_soup(self, url: str) -> BeautifulSoup:
        """Fetches a URL and returns a parsed BeautifulSoup tree."""
        response = self.client.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def extract_title(self, soup: BeautifulSoup) -> str:
        """Extracts the best page title from <title> or <h1>."""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return "Untitled Page"

    def extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extracts the <meta name='description'> or og:description."""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()

        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return og_desc["content"].strip()

        return None

    def clean_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Creates a clone of soup with scripts, styles, and footers removed."""
        # Using a shallow copy or decomposing in-place on a parsed tree
        for tag in soup.find_all(self.BOILERPLATE_TAGS):
            tag.decompose()
        return soup

    def extract_main_paragraphs(self, soup: BeautifulSoup, max_paragraphs: int = 5) -> List[str]:
        """
        Extracts key content paragraphs.
        Prioritizes semantic tags: <article>, <main>, or .content divs.
        """
        # Look for article or main tag first
        container = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=lambda c: c and any(k in c.lower() for k in ["content", "post", "entry"]))
            or soup.body
        )

        if not container:
            return []

        paragraphs = []
        for p in container.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            # Filter out tiny snippets (e.g. "Share this", "By admin")
            if len(text) > 40:
                paragraphs.append(text)
                if len(paragraphs) >= max_paragraphs:
                    break

        return paragraphs

    def extract_apply_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Locates external links that represent the actual 'Apply Now' or official portal.
        Converts relative links to full URLs.
        """
        candidate_links = []
        base_domain = urlparse(base_url).netloc

        keywords = ["apply", "application", "register", "official link", "portal", "submit"]

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            anchor_text = a_tag.get_text(strip=True).lower()
            href_lower = href.lower()

            # Ignore empty or javascript anchors
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Check if anchor text or href matches application keywords
            if any(k in anchor_text for k in keywords) or any(k in href_lower for k in ["/apply", "apply-now"]):
                # Convert relative links (like /apply) to absolute (https://site.com/apply)
                full_url = urljoin(base_url, href)
                target_domain = urlparse(full_url).netloc

                # We especially care about external links leading to the actual university/employer
                candidate_links.append(full_url)

        # Deduplicate while preserving order
        unique_links = []
        for link in candidate_links:
            if link not in unique_links:
                unique_links.append(link)

        return unique_links

    def extract_key_highlights(self, soup: BeautifulSoup, max_items: int = 8) -> List[str]:
        """
        Extracts key bullet points from <li> tags (programme details, eligibility, benefits).
        Filters out boilerplate or overly long items.
        """
        container = soup.find("article") or soup.find("main") or soup
        highlights = []

        for li in container.find_all("li"):
            text = li.get_text(strip=True)
            if 5 < len(text) < 150:
                highlights.append(text)
                if len(highlights) >= max_items:
                    break

        return highlights

    def scrape(self, url: str) -> ScrapedWebPage:
        """Main method: fetches the page, cleans it, and extracts structured data."""
        raw_soup = self.fetch_soup(url)
        title = self.extract_title(raw_soup)
        meta_desc = self.extract_meta_description(raw_soup)

        # Clean boilerplate before extracting text & links
        cleaned_soup = self.clean_soup(raw_soup)

        h1 = cleaned_soup.find("h1")
        main_heading = h1.get_text(strip=True) if h1 else ""

        paragraphs = self.extract_main_paragraphs(cleaned_soup)
        highlights = self.extract_key_highlights(cleaned_soup)
        apply_links = self.extract_apply_links(cleaned_soup, base_url=url)

        return ScrapedWebPage(
            url=url,
            title=title,
            meta_description=meta_desc,
            main_heading=main_heading,
            summary_paragraphs=paragraphs,
            key_highlights=highlights,
            apply_links=apply_links,
        )
