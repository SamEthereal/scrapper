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

### 2. Run the Web Dashboard

Launch the interactive web UI:

```bash
uv run main.py ui
```
Then open your browser to **http://127.0.0.1:8000**!

---

### 3. CLI Commands (Terminal Mode)

#### 🎓 Scholarships
```bash
uv run main.py scrape                      # Scrape Telegram & enrich with web portals
uv run main.py list                        # List all saved scholarships
uv run main.py search Spain                # Search by keyword or country
uv run main.py closing-soon --days 60      # Scholarships closing in next 60 days
uv run main.py filter --country UK --level PhD
```

#### 💼 Remote & 4-Day Jobs
```bash
uv run main.py jobs scrape                 # Scrape 50 live remote jobs from 4dayweek.io
uv run main.py jobs list                   # List all stored jobs
uv run main.py jobs search Security        # Search by role, skill, or company
uv run main.py jobs filter --salary        # Filter for jobs with listed compensation
uv run main.py jobs filter --min-score 90  # High work-life balance jobs
```

---

## Roadmap

- [x] Public Telegram channel scraping (`scrapers/telegram_scraper.py`)
- [x] Scholarship post parser & opportunity classifier (`parsers/scholarship_parser.py`)
- [ ] Direct web page scraper for opportunity URLs (`scrapers/web_scraper.py`)
- [ ] SQLite database storage with deduplication (`storage/db.py`)
- [ ] Job / work board scraper and parser (`parsers/job_parser.py`)
- [ ] Filtering, sorting, and export (CSV, JSON, SQLite)
