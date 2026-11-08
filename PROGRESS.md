# Project Continuity & Learning Progress

> **For Antigravity on any PC:** Read this file to instantly resume our development and pair-programming context without losing history.

---

## 1. Project Goal
Build a dual **Web Scraper & Telegram Scraper** for:
1. **Scholarship Opportunities**: Telegram channels (e.g., `@OHUB4AllET`) + online scholarship sites.
2. **Work / Job Postings**: Tech and employment channels + online job boards.
3. **Downstream Features**: Local storage (SQLite), deduplication, searching, filtering, and sorting.

---

## 2. Tech Stack & Environment
- **Language:** Python 3.10+ / 3.11
- **Package Manager:** `uv`
- **HTTP Client:** `httpx` (with follow redirects & standard browser headers)
- **HTML Parsing:** `beautifulsoup4`
- **Data Validation & Schemas:** `pydantic`
- **CLI & Output:** `rich`

---

## 3. Completed Milestones

### Milestone 1: Zero-Credentials Telegram Scraping
- **Location:** `scrapers/telegram_scraper.py`
- **Concept:** Telegram serves public channel previews via `https://t.me/s/<channel_name>`. No Telegram API key, bot token, or phone number required.
- **Data Model:** `RawTelegramPost` stores `post_id`, `channel_name`, `url`, `date`, `text`, and `links`.

### Milestone 2: Post Parsing & Classification (Student Exercise)
- **Location:** `parsers/scholarship_parser.py`
- **Opportunity Detection:** Distinguishes genuine opportunities (`scholarship`, `fellowship`, `phd`, etc.) from service ads/discounts (`ቅናሽ`, consultancy promos).
- **Deadline Extraction:** Scans text with regex `re.search(r"DEADLINE:\s*(.+)", text, re.IGNORECASE)`.
- **Link Filtering:** Cleans out social media domains (`t.me`, `instagram.com`, `tiktok.com`, `linkedin.com`, `facebook.com`) to extract the genuine application URL (e.g. `https://opportunities.ohubet.com/...`).

### Milestone 3: General Web Scraper Foundation & Highlight Extraction
- **Location:** `scrapers/web_scraper.py`
- **Boilerplate Cleaning:** Strips `<script>`, `<style>`, `<nav>`, `<footer>` using BeautifulSoup's `.decompose()` method.
- **Content & Action Extraction:** Extracts semantic titles, meta descriptions, body paragraphs, and resolves relative URLs into absolute Call-To-Action (CTA) application portal links with `urllib.parse.urljoin`.
- **List & Highlights Extractor (Student Implementation):** Extracts structured bullets from `<li>` tags (e.g. Host institution, location, funding, tuition coverage).
- **End-to-End Test:** Scrapes `@OHUB4AllET` Telegram channel, detects specific opportunity links (e.g. CRG Fellowships in Spain, Caltech SURF in the US), deep-scrapes the webpage, and extracts the direct official university portal (`crg.eu`, `caltech.edu`).

---

## 4. Immediate Next Steps (Pick Up Here)

1. **Option A: Build `scrapers/web_scraper.py`**
   - Take the extracted application URLs (like `https://opportunities.ohubet.com/opportunities/...`) and scrape the full external webpage details (eligibility, benefits, deadline confirmation, application form link).
2. **Option B: Build `storage/db.py` (SQLite)**
   - Persist scraped posts into a local SQLite database with unique constraint on `(channel_name, post_id)` to prevent duplicates across multiple scraper runs.
3. **Option C: Add Search, Filter & CLI Commands**
   - Build CLI commands to filter by keyword, upcoming deadlines, or opportunity type.

---

## 5. How to Continue on Another PC

When you clone this repo on your work PC:
1. Clone the repository:
   ```bash
   git clone https://github.com/SamEthereal/scrapper.git
   cd scrapper
   ```
2. Run `uv sync` to install dependencies into the virtual environment automatically.
3. Open Antigravity in that folder and start a new chat with:
   > *"I've pulled the repo on my work PC. Read PROGRESS.md and let's continue where we left off."*

