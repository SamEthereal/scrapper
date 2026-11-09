"""Telegram Channel Scraper.

Scrapes public Telegram channels using their web preview endpoint (`https://t.me/s/<channel_name>`).
No API keys or Telegram accounts required!
"""

from dataclasses import dataclass, field
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup


@dataclass
class RawTelegramPost:
    """Represents a raw scraped post from a Telegram channel."""
    post_id: str
    channel_name: str
    url: str
    date: str
    text: str
    links: List[str] = field(default_factory=list)


class TelegramScraper:
    """Scrapes messages from public Telegram channels via web previews."""

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    def scrape_channel(self, channel_identifier: str, limit: int = 10) -> List[RawTelegramPost]:
        """
        Scrapes the most recent posts from a public channel.
        
        Args:
            channel_identifier: Channel username (e.g. 'OHUB4AllET' or 'https://t.me/OHUB4AllET')
            limit: Maximum number of recent posts to return.
            
        Returns:
            List of RawTelegramPost objects.
        """
        # Clean channel name if full URL was passed
        channel_name = channel_identifier.strip("/").split("/")[-1].replace("@", "")
        preview_url = f"https://t.me/s/{channel_name}"

        # 1. FETCH: Make an HTTP GET request with a forgiving timeout
        response = httpx.get(
            preview_url,
            headers=self.headers,
            follow_redirects=True,
            timeout=25.0,
        )
        response.raise_for_status()

        # 2. PARSE: Convert the raw HTML into a searchable tree with BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")

        # 3. LOCATE: Find all message containers
        message_elements = soup.find_all("div", class_="tgme_widget_message")

        posts: List[RawTelegramPost] = []

        # Iterate over the messages (taking the most recent ones up to `limit`)
        for elem in message_elements[-limit:]:
            # Message permalink & ID
            date_anchor = elem.find("a", class_="tgme_widget_message_date")
            post_url = date_anchor.get("href", "") if date_anchor else ""
            post_id = post_url.split("/")[-1] if post_url else ""

            # Publication timestamp
            time_tag = elem.find("time")
            date_str = time_tag.get("datetime", "") if time_tag else ""

            # Text content
            text_elem = elem.find("div", class_="tgme_widget_message_text")
            if text_elem:
                text = text_elem.get_text(separator="\n").strip()
                # Extract all hyperlinked URLs inside the text
                links = [a.get("href") for a in text_elem.find_all("a") if a.get("href")]
            else:
                text = "[No Text / Media or Sticker]"
                links = []

            posts.append(
                RawTelegramPost(
                    post_id=post_id,
                    channel_name=channel_name,
                    url=post_url,
                    date=date_str,
                    text=text,
                    links=links,
                )
            )

        return posts
