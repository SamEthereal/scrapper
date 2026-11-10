"""Job parser for extracting structured JobItem instances from job boards and cards."""

from typing import List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pydantic import BaseModel


class JobItem(BaseModel):
    """Structured representation of a job listing."""
    title: str
    company: str
    location: str
    is_remote: bool = True
    salary: Optional[str] = None
    schedule: Optional[str] = None
    work_life_score: Optional[int] = None
    url: str
    source: str = "4dayweek.io"


def extract_salary(strings: List[str]) -> Optional[str]:
    """Extracts salary string (e.g. '$160k – $190k' or '€3,800 – €4,600') from card strings."""
    for item in strings:
        # Note: in Python, startswith takes a tuple of prefixes: (prefix1, prefix2)
        if item.startswith(("$", "€", "£")):
            return item.strip()
    return None


def is_job_remote(location: str) -> bool:
    """Checks whether the job is remote by inspecting the location text."""
    return "remote" in location.lower()


def extract_schedule(strings: List[str]) -> Optional[str]:
    """Extracts schedule details like '4 Day Work Week (32hrs)'."""
    for item in strings:
        if "day work week" in item.lower():
            return item.strip()
    return None


def extract_work_life_score(strings: List[str]) -> Optional[int]:
    """Extracts work-life balance score (0-100) if present."""
    for i, item in enumerate(strings):
        if "work-life score" in item.lower() and i + 1 < len(strings):
            candidate = strings[i + 1].strip()
            if candidate.isdigit():
                return int(candidate)
    return None


def parse_job_card(card: BeautifulSoup, base_url: str = "https://4dayweek.io") -> Optional[JobItem]:
    """Parses a job card BeautifulSoup element into a structured JobItem."""
    a_tag = card.find("a", href=lambda h: h and "/job/" in h)
    if not a_tag:
        return None

    title = a_tag.get_text(strip=True)
    job_url = urljoin(base_url, a_tag["href"])

    strings = list(card.stripped_strings)
    if not strings:
        return None

    # On 4dayweek cards: strings[0] is Title, strings[1] is Company, strings[2] is Location
    company = strings[1] if len(strings) > 1 else "Unknown Company"
    location = strings[2] if len(strings) > 2 else "Remote"

    salary = extract_salary(strings)
    remote = is_job_remote(location)
    schedule = extract_schedule(strings)
    score = extract_work_life_score(strings)

    return JobItem(
        title=title,
        company=company,
        location=location.replace("·", "").strip(),
        is_remote=remote,
        salary=salary,
        schedule=schedule,
        work_life_score=score,
        url=job_url,
        source="4dayweek.io",
    )
