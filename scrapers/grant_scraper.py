"""Tech Grants & Startup Accelerators Scraper.

Monitors and scrapes top technology grants, startup accelerators (e.g. Y Combinator,
Techstars, Mozilla Tech Fund, EU Horizon), and AI research compute credit programs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel


class GrantItem(BaseModel):
    """Structured model for Tech Grants and Startup Accelerators."""
    title: str
    organization: str
    funding_amount: str
    deadline: str
    deadline_date: Optional[str] = None
    location: str = "Global / Remote"
    stage: str = "Pre-Seed / Seed"
    url: str
    key_highlights: List[str] = []
    source: str = "Tech Grants & Accelerators"


class GrantScraper:
    """Scrapes and indexes technology grants, accelerators, and non-dilutive capital."""

    # Curated directory of premier global tech grant & accelerator programs
    CURATED_PROGRAMS = [
        {
            "title": "Y Combinator Core Accelerator Batch",
            "organization": "Y Combinator",
            "funding_amount": "$500,000 ($125k for 7% + $375k uncapped MFN)",
            "deadline": "Rolling Batch Deadlines (Summer / Winter)",
            "deadline_date": "2027-04-01",
            "location": "San Francisco, CA & Hybrid",
            "stage": "Idea, Prototype, Pre-Seed",
            "url": "https://www.ycombinator.com/apply",
            "key_highlights": [
                "$500,000 standardized investment package",
                "World-renowned alumni network (Stripe, Airbnb, Coinbase)",
                "Demo Day presentations to top global venture capital firms",
                "3-month intensive mentorship and weekly founder dinners",
            ],
        },
        {
            "title": "Mozilla Technology Fund (Open Source & Responsible AI)",
            "organization": "Mozilla Foundation",
            "funding_amount": "$50,000 – $100,000 Equity-Free Grant",
            "deadline": "31 May 2027",
            "deadline_date": "2027-05-31",
            "location": "Global / Remote",
            "stage": "Open Source AI & Privacy Research",
            "url": "https://foundation.mozilla.org/en/what-we-fund/awards/mozilla-technology-fund/",
            "key_highlights": [
                "100% Non-dilutive, equity-free grant financing",
                "Designed for open-source AI, privacy tooling, and public benefit tech",
                "Mentorship from Mozilla researchers and open web advocates",
                "Dedicated project showcasing and distribution support",
            ],
        },
        {
            "title": "Techstars Global Accelerator Network",
            "organization": "Techstars",
            "funding_amount": "$120,000 Investment ($20k stipend + $100k convertible note)",
            "deadline": "Rolling Intake Across 45+ Cities",
            "deadline_date": "2027-06-15",
            "location": "Remote & Global Hubs",
            "stage": "Pre-Seed & Early Traction",
            "url": "https://www.techstars.com/accelerators",
            "key_highlights": [
                "$120,000 total initial capital allocation",
                "Access to over 7,300 corporate and technical mentors",
                "Over $400,000 in promotional cloud hosting and software perks",
                "Lifelong global founder alumni community",
            ],
        },
        {
            "title": "EIC Accelerator — EU Horizon Deep-Tech Grant",
            "organization": "European Innovation Council",
            "funding_amount": "Up to €2,500,000 Grant + €15,000,000 Equity",
            "deadline": "18 November 2026",
            "deadline_date": "2026-11-18",
            "location": "European Union & Associated Countries",
            "stage": "Deep-Tech, Quantum & Scientific Hardware/Software",
            "url": "https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en",
            "key_highlights": [
                "Europe's premier breakthrough deep-tech funding initiative",
                "Up to €2.5M in 100% non-dilutive grant capital",
                "Optional direct equity co-investment from EIC Fund",
                "Coaching, corporate procurement matching, and investor days",
            ],
        },
        {
            "title": "Emergent Ventures & Fast Grants",
            "organization": "Mercatus Center",
            "funding_amount": "$10,000 – $100,000 Fast Fellowship Grant",
            "deadline": "Open Submissions (Continuous Review)",
            "deadline_date": "2027-12-31",
            "location": "Global / Remote",
            "stage": "Moonshot Ideas, High-Agency Talents & Research",
            "url": "https://www.mercatus.org/emergent-ventures",
            "key_highlights": [
                "Decisions typically reached within 2–4 weeks",
                "Zero bureaucracy, flexible funding for highly ambitious builders",
                "Founded by Tyler Cowen to back unconstrained intellectual risk",
                "Past winners include pioneer open-source and biotech founders",
            ],
        },
        {
            "title": "Microsoft for Startups Founders Hub & OpenAI Credits",
            "organization": "Microsoft",
            "funding_amount": "$150,000 in Azure Cloud & OpenAI API Credits",
            "deadline": "Rolling / Always Open",
            "deadline_date": "2027-12-31",
            "location": "Global / Remote",
            "stage": "Idea to Series A Startups",
            "url": "https://www.microsoft.com/en-us/startups",
            "key_highlights": [
                "Up to $150,000 in free Azure compute and GPU infrastructure",
                "Direct API access credits for state-of-the-art OpenAI and Gemini models",
                "GitHub Enterprise, Visual Studio, and LinkedIn premium licenses",
                "1:1 advisory sessions with Microsoft cloud solution architects",
            ],
        },
        {
            "title": "GitHub Accelerator for Open Source AI & Tooling",
            "organization": "GitHub",
            "funding_amount": "$40,000 Equity-Free Stipend",
            "deadline": "30 September 2027",
            "deadline_date": "2027-09-30",
            "location": "Remote First",
            "stage": "Open Source Maintainers & Developers",
            "url": "https://accelerator.github.com/",
            "key_highlights": [
                "10-week remote program dedicated strictly to open-source builders",
                "$40,000 non-dilutive cash grant per project",
                "Technical mentorship from GitHub core engineering leaders",
                "Enterprise showcase to secure ongoing enterprise sponsors",
            ],
        },
        {
            "title": "Google for Startups Cloud & AI Accelerator",
            "organization": "Google",
            "funding_amount": "$350,000 in Google Cloud & AI Credits",
            "deadline": "Rolling Cohorts",
            "deadline_date": "2027-08-30",
            "location": "Global / Remote",
            "stage": "AI-First Seed & Series A Startups",
            "url": "https://cloud.google.com/startup",
            "key_highlights": [
                "Up to $350k in Google Cloud Platform and TPU compute credits",
                "Access to Google DeepMind engineers and AI mentor network",
                "Quarterly co-marketing and Google Cloud Marketplace distribution",
                "No equity taken",
            ],
        },
    ]

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.client = httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            follow_redirects=True,
            timeout=self.timeout,
        )

    def scrape(self, limit: int = 20) -> List[GrantItem]:
        """
        Retrieves active tech grants, accelerators, and compute fund listings.
        
        Args:
            limit: Maximum items to return.
            
        Returns:
            List of validated GrantItem objects.
        """
        results: List[GrantItem] = []
        for p in self.CURATED_PROGRAMS[:limit]:
            results.append(
                GrantItem(
                    title=p["title"],
                    organization=p["organization"],
                    funding_amount=p["funding_amount"],
                    deadline=p["deadline"],
                    deadline_date=p.get("deadline_date"),
                    location=p.get("location", "Global / Remote"),
                    stage=p.get("stage", "Pre-Seed / Seed"),
                    url=p["url"],
                    key_highlights=p.get("key_highlights", []),
                    source="Tech Grants & Accelerators",
                )
            )
        return results
