# Opportunity Scraper (Web & Telegram)

A modular, extensible scraper and parser for extracting scholarship and job opportunities from Telegram channels and web pages using Python, `httpx`, `BeautifulSoup4`, and `Pydantic`.

---

## Features

- **Telegram Public Channel Scraper:** Scrapes public Telegram channel previews (`https://t.me/s/<channel>`) with **zero API keys or phone numbers required**.
- **Rule-Based Opportunity Extraction:**
  - Identifies legitimate opportunities vs. advertisements/promotions.
  - Extracts application deadlines via regex patterns.
  - Filters out social media/promo links to pinpoint the real application URL.
- **Modern Python Tooling:** Built with `uv` for lightning-fast package management and virtual environments.
- **Rich Terminal UI:** Formatted output and summary tables powered by `rich`.

---

## Project Structure

```
Web Scrapper/
├── scrapers/
│   └── telegram_scraper.py     # Public Telegram channel preview scraper
├── parsers/
│   └── scholarship_parser.py   # Extracts titles, deadlines, links & opportunity flags
├── main.py                     # Entry point & terminal dashboard
├── pyproject.toml              # Dependencies & project metadata
├── uv.lock                     # Locked dependency tree
└── README.md
```

---

## Quickstart

### 1. Prerequisites

Install `uv` (recommended):
- **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 2. Run the Scraper

Clone the repo and run:

```bash
# Sync/install dependencies automatically and run
uv run main.py
```

---

## Roadmap

- [x] Public Telegram channel scraping (`scrapers/telegram_scraper.py`)
- [x] Scholarship post parser & opportunity classifier (`parsers/scholarship_parser.py`)
- [ ] Direct web page scraper for opportunity URLs (`scrapers/web_scraper.py`)
- [ ] SQLite database storage with deduplication (`storage/db.py`)
- [ ] Job / work board scraper and parser (`parsers/job_parser.py`)
- [ ] Filtering, sorting, and export (CSV, JSON, SQLite)
