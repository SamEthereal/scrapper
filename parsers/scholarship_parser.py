"""Parser for Telegram scholarship posts."""

import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from scrapers.telegram_scraper import RawTelegramPost


class OpportunityItem(BaseModel):
    """Structured representation of an extracted scholarship/job opportunity."""
    post_id: str
    channel_name: str
    post_url: str
    date: str
    title: str
    deadline: Optional[str] = None
    deadline_date: Optional[str] = None  # Normalized ISO date (YYYY-MM-DD) for sorting & filtering
    apply_url: Optional[str] = None
    is_opportunity: bool = False
    raw_text: str


# Social and channel promo domains to ignore when looking for application links
SPAM_DOMAINS = [
    "t.me",
    "instagram.com",
    "tiktok.com",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "google.com/maps",
    "maps.google.com",
]

OPPORTUNITY_KEYWORDS = [
    "scholarship",
    "fellowship",
    "studentship",
    "internship",
    "phd",
    "master's",
    "postdoctoral",
    "fully funded",
]


def normalize_deadline(raw_deadline: Optional[str]) -> Optional[str]:
    """
    Converts human-readable deadline strings into ISO 8601 YYYY-MM-DD format.
    Example: '7 JANUARY 2027' -> '2027-01-07'
    """
    if not raw_deadline:
        return None

    # 1. Day Month Year pattern: e.g. '7 JANUARY 2027' or '31 Dec 2026'
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw_deadline)
    if match:
        day, month, year = match.groups()
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(f"{day} {month.title()} {year}", fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # 2. ISO format YYYY-MM-DD
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw_deadline)
    if match:
        y, mon, d = match.groups()
        return f"{int(y):04d}-{int(mon):02d}-{int(d):02d}"

    return None


def parse_post(post: RawTelegramPost) -> OpportunityItem:
    """Parses a raw Telegram post into a structured OpportunityItem."""
    text = post.text
    text_lower = text.lower()

    # 1. Check if it's an opportunity or an ad
    is_opportunity = any(word in text_lower for word in OPPORTUNITY_KEYWORDS)

    # 2. Extract Deadline & normalize to ISO YYYY-MM-DD
    deadline_match = re.search(r"DEADLINE:\s*(.+)", text, re.IGNORECASE)
    deadline = deadline_match.group(1).strip() if deadline_match else None
    deadline_date = normalize_deadline(deadline)

    # 3. Filter for real application links (ignoring social media and Telegram hashtag search queries)
    valid_links = [
        link for link in post.links
        if link.startswith(("http://", "https://"))
        and not any(domain in link.lower() for domain in SPAM_DOMAINS)
        and "?q=" not in link
    ]
    apply_url = valid_links[0] if valid_links else None

    # 4. Extract title: First non-empty line after cleaning emojis/symbols
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = ""
    for line in lines:
        if len(line) > 10:
            title = line
            break
    if not title and lines:
        title = lines[0]

    return OpportunityItem(
        post_id=post.post_id,
        channel_name=post.channel_name,
        post_url=post.url,
        date=post.date,
        title=title,
        deadline=deadline,
        deadline_date=deadline_date,
        apply_url=apply_url,
        is_opportunity=is_opportunity,
        raw_text=text,
    )
