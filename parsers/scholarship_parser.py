"""Parser for Telegram scholarship posts."""

import re
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


def parse_post(post: RawTelegramPost) -> OpportunityItem:
    """Parses a raw Telegram post into a structured OpportunityItem."""
    text = post.text
    text_lower = text.lower()

    # 1. Check if it's an opportunity or an ad
    is_opportunity = any(word in text_lower for word in OPPORTUNITY_KEYWORDS)

    # 2. Extract Deadline (re.search scans the whole text, re.IGNORECASE handles case)
    deadline_match = re.search(r"DEADLINE:\s*(.+)", text, re.IGNORECASE)
    deadline = deadline_match.group(1).strip() if deadline_match else None

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
        # Pick the first substantial line (e.g., more than 10 characters)
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
        apply_url=apply_url,
        is_opportunity=is_opportunity,
        raw_text=text,
    )
