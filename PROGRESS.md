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

### Milestone 4: SQLite Database Persistence & Search Engine
- **Location:** `storage/db.py`
- **Schema & Indexes:** `opportunities` table with columns for `channel_name`, `post_id`, `title`, `deadline`, `apply_url`, `official_portal`, `key_highlights` (JSON), and `is_opportunity`.
- **Deduplication:** Enforces `UNIQUE(channel_name, post_id)` with `INSERT OR IGNORE`. Repeated scraper runs silently skip existing entries.
- **Dictionary Access:** Uses `conn.row_factory = sqlite3.Row` for intuitive column-by-name access.
- **Search Query (Student Implementation):** Parameterized `LIKE` query across both `title` and `key_highlights` (`f"%{keyword}%"`).

### Milestone 5: Advanced Filtering, Sorting & Date Normalization
- **Deadline Normalization:** `normalize_deadline()` in `parsers/scholarship_parser.py` maps human date strings (`"7 JANUARY 2027"`, `"31 Dec 2026"`) to ISO 8601 `YYYY-MM-DD`.
- **Dynamic Query Builder:** `filter_opportunities()` in `storage/db.py` supports combining multiple filters: `--country`, `--level` (PhD, Master), `--has-deadline`, and `--open-only`.
- **Chronological Sorting:** Safe column whitelisting supporting `--sort deadline --order asc` (closing soonest). Pushes `NULL` deadlines to the bottom with SQL `CASE WHEN`.
- **Closing Soon Utility (Student Implementation):** `get_closing_soon(days=N)` query using SQLite date math `date('now', '+N days')`.

### Milestone 6: Phase 2 — Remote & 4-Day Work Job Scraper
- **Location:** `parsers/job_parser.py` & `scrapers/job_scraper.py`
- **Data Model:** `JobItem` capturing `title`, `company`, `location`, `is_remote`, `salary`, `schedule`, `work_life_score`, `url`, and `source`.
- **Job Card Extraction (Student Implementation):**
  - Robust DOM targeting via `data-testid="job-card"`.
  - `extract_salary()`: captures currencies (`$`, `€`, `£`) across card text tokens.
  - `is_job_remote()`: dynamic remote work detector.
  - `extract_schedule()` and `extract_work_life_score()`: extracts 4-day week terms and 0-100 balance ratings.
- **SQLite Storage & Deduplication:** `jobs` table with `UNIQUE(url)` index.
- **Job CLI Suite:**
  - `uv run main.py jobs scrape` (pulls 50 live jobs from 4dayweek.io)
  - `uv run main.py jobs search <role>` (e.g. `Design`, `Engineer`, `Buffer`)
  - `uv run main.py jobs filter --salary` (only jobs with listed compensation)
  - `uv run main.py jobs filter --min-score 90` (high work-life rating)

### Milestone 7: Interactive Web Dashboard & REST API (FastAPI)
- **Location:** `ui/app.py` & `ui/templates/index.html`
- **Backend API:** Built with FastAPI and Uvicorn. Exposes REST endpoints:
  - `GET /`: Serves the responsive SPA dashboard.
  - `GET /api/stats`: Real-time counts of scholarships and jobs.
  - `GET /api/opportunities`: Search, country/level filters, and closing-soon deadline queries.
  - `GET /api/jobs`: Search, salary filter, and work-life balance ranking.
  - `POST /api/scrape/scholarships` & `POST /api/scrape/jobs`: 1-click live sync from the web UI.
- **Frontend UI:** Modern responsive dashboard styled with Tailwind CSS and FontAwesome icons:
  - Tab switching between Scholarships and Jobs.
  - Live instant debounced search bar.
  - Quick filter pills (UK, Spain, USA, PhD, High Work-Life, Verified Salary).
  - Clean card grids with color-coded badges, deadlines, and direct apply portal buttons.
- **Launch Command:** `uv run main.py ui` &rarr; opens `http://127.0.0.1:8000`.

### Milestone 8: Automated Background Scheduler & Alert Engine
- **Location:** `services/scheduler.py`
- **Scheduler Engine:** Uses `schedule` to run recurring scrape cycles across all sources (Telegram scholarships + 4dayweek remote jobs).
- **Deduplication Alert:** Detects only *newly discovered* opportunities and jobs (`is_new == True`).
- **Activity Logging:** Records timestamped cycle events and new item listings to `scraper_activity.log`.
- **Desktop Alerts:** Dispatches non-blocking notifications to the user whenever new posts or jobs are discovered.
- **CLI Automation Commands:**
  - `uv run main.py auto --interval 60` (runs standing background loop every N minutes)
  - `uv run main.py auto --once` (executes a single automated cycle & exits, ideal for OS cron / Task Scheduler).
- **Full CLI Suite:** Powered by `argparse` in `main.py` with commands: `scrape`, `list`, `search`, `filter`, and `closing-soon`.

---

### Milestone 9: Dashboard Redesign (Mockup Adoption & Bento-Grid Layout)
- **Location:** `ui/templates/index.html` & `ui/app.py`
- **Design Inspiration:** Adopted user-provided clinical/modern bento-grid layout (`media_1794385887702_fdb5ea5f.jpg`).
- **Layout Architecture (3-Column Grid):**
  - **Top Floating Pill Navigation:** Capsule bar with `Overview`, `Scholarships`, `Jobs (4-Day)`, `News & Tech`, `Scrapers`, and 1-click live `Sync` trigger with spin animation.
  - **Left Column (Active Stream & Favorites):**
    - Dynamic stream list of loaded opportunities and jobs with filter toggle (`All`, `Opps`, `Jobs`).
    - LocalStorage-backed `Favorites` list for 1-click starring/bookmarking.
    - Quick Scrape URL trigger button.
  - **Center Column (Hero Spotlight & 3D Visual Artwork):**
    - Large rounded showcase card with active status chip, deadline/company subheader, and direct actions (Star ⭐, Copy URL 🔗).
    - Holographic 3D art card displaying opportunity badge, title, and intake status.
    - Floating 3-row spec table (`01`, `02`, `03`) displaying compensation/funding, work-life/stipend, and location/eligibility.
    - Direct CTA button (`Apply to Opportunity`) linked directly to the application portal.
  - **Right Column (Top Opportunities, AI Assistant & History):**
    - Filter chips (`⏳ Closing Soon`, `🎓 PhD Only`, `💰 Top Salary`, `🌟 90+ Score`).
    - Conversational Scraper Agent input bubble (`+ Type filter e.g. 'Spain' or 'Buffer'`).
    - Live `History` log card parsing recent events from `scraper_activity.log`.
- **Theming:** Dual warm ceramic cream (`#f2efe9`) and dark obsidian (`#0c1017`) modes with custom scrollbars, glassmorphism, and persistent theme detection.

### Milestone 10: Application Pipeline (Kanban Tracker) & Calendar Sync Engine
- **Location:** `storage/db.py`, `ui/app.py`, `ui/templates/index.html`
- **Database Schema:** `applications` table in SQLite (`id`, `item_type`, `item_id`, `title`, `subtitle`, `deadline_or_salary`, `deadline_date`, `url`, `status`, `notes`, `created_at`, `updated_at`).
- **REST Endpoints:**
  - `GET /api/pipeline`: Returns all tracked applications.
  - `POST /api/pipeline`: Adds an opportunity or job to the pipeline with automatic conflict handling.
  - `PATCH /api/pipeline/{app_id}`: Updates stage status (`saved`, `applied`, `interview`, `offer`) or personal notes.
  - `DELETE /api/pipeline/{app_id}`: Removes an application from the tracker.
  - `GET /api/calendar/{opp_id}.ics`: Generates an RFC 5545 standard iCalendar `.ics` file with an embedded 3-day alarm reminder.
- **Frontend Kanban Board:**
  - Dedicated **Pipeline** tab in the top capsule navigation with a real-time badge count.
  - 4-column Bento Kanban board:
    1. 📌 **Saved & To Apply**
    2. 📨 **Applied & In Review**
    3. 🎯 **Interview & Test**
    4. 🏆 **Offer & Acceptance**
  - **Live Stage Counters:** Instant ribbon showing Total, Saved, Applied, Interview, and Offer counts.
  - **Deadline Countdowns:** Dynamic badge highlighting remaining days (`⏳ in 14 days`, `⚠️ Today!`, or `Elapsed`) with color-coded urgency.
  - **1-Click Calendar Sync:** Direct button to prefill Google Calendar or download `.ics` event files.
  - **Inline Notes:** Editable personal notes per application saved to SQLite.
  - **Spotlight Integration:** The central hero spotlight now features a dynamic **`[Track in Pipeline]`** status button and **`[📅 Calendar]`** dropdown.

### Milestone 11: Candidate AI Profile Matcher & 1-Click Application Copilot
- **Location:** `storage/db.py`, `services/matcher.py`, `services/copilot.py`, `ui/app.py`, `ui/templates/index.html`, `main.py`
- **Database Schema:** `user_profiles` table in SQLite (`id`, `full_name`, `email`, `title`, `skills`, `degree`, `experience_years`, `preferred_locations`, `target_roles`, `bio`, `updated_at`). Seeded with active developer profile.
- **AI Matching Engine (`services/matcher.py`):**
  - Multi-dimensional fit scoring algorithm (0–100%):
    - **Skill Overlap (45 pts):** Regex boundary matching between candidate skills and listings.
    - **Role / Title Alignment (30 pts):** Overlap between target titles and scraped roles.
    - **Work Style & Location (15 pts):** Remote preference alignment and geographic targeting.
    - **Degree & Seniority (10 pts):** Academic qualification / experience year mapping.
  - Returns `score`, `grade` (*Exceptional Match*, *Strong Match*, *Good Fit*, *Potential Fit*), `color`, `matched_skills`, and personalized justifications (`reasons`).
- **1-Click Application Copilot (`services/copilot.py`):**
  - Synthesizes personalized, high-converting **Cover Letters** (for jobs) and **Statements of Purpose** (for scholarships/fellowships).
  - Integrates matched skills, candidate background, and listings' specific cultural highlights (e.g. 4-day week, work-life rating, research lab focus).
- **FastAPI REST Endpoints (`ui/app.py`):**
  - `GET /api/profile`: Retrieves active candidate profile and skills list.
  - `POST /api/profile`: Updates profile data and triggers immediate re-scoring.
  - `POST /api/copilot/generate`: Generates tailored Markdown and plain-text application drafts with metadata.
  - Enriched `/api/opportunities` and `/api/jobs` with automatic `match` data and `sort_by=match`.
- **Bento Web Dashboard UI (`ui/templates/index.html`):**
  - Header profile button with user initials badge opening the Candidate AI Profile Modal.
  - Interactive profile modal with real-time tag previews, skills chip editing, and 1-click re-scoring.
  - Stream list cards with color-coded AI match percentage pills (`🎯 98% Fit`).
  - Hero spotlight featuring the **AI Match Radar** with matched skills and a glowing **`[1-Click Copilot]`** button.
  - Full-featured Copilot modal with tone switching, document reader/editor, copy to clipboard, `.md` download, and 1-click **"Save to Pipeline with Letter"**.
  - Right-column quick filter chip: **`🎯 Top AI Match`**.
- **CLI Suite (`main.py`):**
  - `uv run main.py profile view`
  - `uv run main.py profile set --skills "Python, Docker, ML"`
  - `uv run main.py match jobs`
  - `uv run main.py match opps`
  - `uv run main.py copilot --type job --id <id> [--save]`

### Milestone 12: Multi-Vertical Scraper Expansion (Pillar 2 - WWR Gigs, Tech Grants & Accelerators)
- **Status:** **Core Architecture Complete & Tested** (UI polish for Scrapers Hub in progress).
- **Location:** `scrapers/wwr_scraper.py`, `scrapers/grant_scraper.py`, `storage/db.py`, `services/matcher.py`, `services/copilot.py`, `ui/app.py`, `main.py`, `ui/templates/index.html`
- **WeWorkRemotely RSS Scraper (`scrapers/wwr_scraper.py`):**
  - Parses live RSS XML feeds from `weworkremotely.com/categories/remote-programming-jobs.rss` and `remote-devops-sysadmin-jobs.rss`.
  - Uses Python's native `xml.etree.ElementTree` with zero third-party C/C++ compilation dependencies (bypassing BeautifulSoup `lxml` requirements).
  - Extracts clean company names, job titles, category tags, regions, descriptions, and direct apply links.
  - Ingests seamlessly into the `jobs` database table.
- **Tech Grants & Startup Accelerators Scraper (`scrapers/grant_scraper.py`):**
  - Scrapes and indexes non-dilutive capital, startup accelerators, research stipends, and cloud compute grants.
  - Built-in live indexer covering **Y-Combinator (YC Batch)**, **Mozilla Technology Fund**, **Techstars Accelerator**, **EU Horizon Europe (EIC Accelerator)**, **Emergent Ventures (Mercatus)**, **Microsoft for Startups ($150k OpenAI credits)**, and **Google for Startups Cloud AI Grant**.
  - Extracts funding amounts ($50k to $2.5M), deadlines, stage targets (Pre-seed, Seed, R&D), categories, eligibility rules, and official application URLs.
- **Grants Storage Layer (`storage/db.py`):**
  - Added `grants` table with unique constraint on `url` (`id`, `title`, `organization`, `amount`, `deadline`, `target_stage`, `category`, `description`, `url`, `eligibility`, `is_grant`, `created_at`).
  - Added helper methods: `save_grant()`, `get_grants()`, `get_grant_by_id()`, `count_grants()`.
- **Grant Fit Matcher & Pitch Proposal Copilot:**
  - `services/matcher.py`: Added `item_type == "grant"` support. Computes 0–100% fit scores comparing candidate skills, target roles, and background against grant focus areas.
  - `services/copilot.py`: Added `generate_grant_proposal()` to automatically synthesize comprehensive Executive Pitch & Grant Applications:
    1. **Executive Summary & Problem Statement**
    2. **Proposed Technical Architecture & Innovation**
    3. **Capital Allocation & Milestones**
    4. **Team & Founder Qualifications**
- **REST Endpoints (`ui/app.py`):**
  - `GET /api/grants`: Search and category filtering for startup funding and grants.
  - `GET /api/sources`: Scraper Health & Registry endpoint returning all active scraper modules, target URLs, health status, and item counts.
  - `POST /api/scrape/wwr`: 1-click live sync for WeWorkRemotely.
  - `POST /api/scrape/grants`: 1-click sync for Tech Grants & Startup Accelerators.
  - `POST /api/copilot/generate`: Expanded to generate grant proposals when `item_type == "grant"`.
  - `GET /api/stats`: Expanded with total grants and registered scraper counts.
- **CLI Commands (`main.py`):**
  - `uv run main.py wwr scrape`
  - `uv run main.py grants scrape`
  - `uv run main.py grants list`
  - `uv run main.py grants search <keyword>`
  - `uv run main.py sources` (displays rich tabular health registry of all 4 scrapers)
  - `uv run main.py copilot --type grant --id <id> [--save]`
- **Bento Dashboard UI (`ui/templates/index.html`):**
  - Added `Grants & Capital` tab in the top pill navigation.
  - Added `Grants` stream toggle pill (`All`, `Opps`, `Jobs`, `Grants`).
  - Grants in hero spotlight display funding amount, target venture stage, eligibility, and a glowing `1-Click Pitch Proposal` button.
  - Placeholder `#scrapers-view` container ready for interactive Scrapers Hub grid.

---

## 4. Architectural Expansion Roadmap (Next Steps)

1. **Finish Milestone 12 UI Polish (Scrapers Hub):**
   - In `ui/templates/index.html`, connect `renderScrapersHub()` to fetch `/api/sources` and display a visual grid of scrapers with live "Run Scraper" buttons and latency stats.
2. **Milestone 13: Push Distribution Channels & Notification Dispatcher:**
   - Automated Telegram bot dispatching instant push alerts to private user channels.
   - Weekly automated digest newsletter generated via email or desktop notification queue.
3. **Milestone 14: User Authentication & Multi-Tenancy:**
   - Add FastAPI Auth (JWT or OAuth2 / GitHub login).
   - Per-user preferences: Saved search alerts, starred items in PostgreSQL/SQLite user table, and resume uploads.

---

## 5. How to Continue on Your Home PC

When you open Antigravity on your home PC, follow these quick steps:

### 1. Pull Latest Changes
```bash
# Pull the latest commits including Milestone 11 & Milestone 12
git pull origin main

# Ensure virtual environment and dependencies are up to date
uv sync
```

### 2. Populate Fresh Local Database
Because `.db` files are kept out of git tracking (`.gitignore`), populate your SQLite database in seconds:
```bash
# Ingest live Telegram scholarships:
uv run main.py scrape

# Ingest 50+ remote 4-day jobs:
uv run main.py jobs scrape

# Ingest WeWorkRemotely gigs:
uv run main.py wwr scrape

# Ingest Tech Grants & Startup Accelerators:
uv run main.py grants scrape

# Verify all sources:
uv run main.py sources
```

### 3. Launch the Bento Web Dashboard
```bash
uv run main.py ui
```
Open **`http://127.0.0.1:8000`** in your browser!

### 4. Prompt to Send Antigravity on Your Home PC:
Copy and paste this exact message into your first chat with Antigravity at home:
> *"I've pulled the latest changes on my home PC and ran `uv sync`. Read `PROGRESS.md` to see what has been accomplished in Milestones 1–12. We have completed the core backend and CLI for Milestone 12 (WWR gigs, Tech Grants scraper, DB schema, Grant Copilot, and API endpoints). Let's finish the frontend Scrapers Hub grid in `index.html` and then move on to Milestone 13!"*

---

## 6. Antigravity Agent Briefing (For the Assistant on Home PC)

> **Agent Context:**
> - **Project:** Dual Telegram & Web Scraper + Interactive Bento-Grid SPA with an Application Pipeline, Candidate AI Profile Matcher, 1-Click Application Copilot, and Multi-Vertical Grants/Jobs Ingestion.
> - **Active Tech Stack:** Python 3.10+, `uv`, `httpx`, `beautifulsoup4`, `fastapi`, `uvicorn`, `sqlite3`, `pydantic`, `schedule`, Tailwind CSS, FontAwesome.
> - **Architecture & Key Files:**
>   - [`scrapers/telegram_scraper.py`](file:///scrapers/telegram_scraper.py): Scrapes Telegram public channel previews (`https://t.me/s/...`) with zero credentials.
>   - [`scrapers/web_scraper.py`](file:///scrapers/web_scraper.py): Deep page scraper; cleans DOM, extracts key highlights (`<li>` bullets), and resolves CTA application URLs.
>   - [`scrapers/job_scraper.py`](file:///scrapers/job_scraper.py): Scrapes 50+ remote listings from `4dayweek.io/remote-jobs`.
>   - [`scrapers/wwr_scraper.py`](file:///scrapers/wwr_scraper.py): XML RSS scraper for WeWorkRemotely remote developer & devops listings.
>   - [`scrapers/grant_scraper.py`](file:///scrapers/grant_scraper.py): Tech Grants & Startup Accelerators indexer ($50k-$2.5M capital programs).
>   - [`storage/db.py`](file:///storage/db.py): SQLite layer (`opportunities.db`) with `opportunities`, `jobs`, `grants`, `applications`, and `user_profiles` tables. Handles deduplication (`UNIQUE`), search, filtering, pipeline tracking, and profile persistence.
>   - [`services/matcher.py`](file:///services/matcher.py): Multi-dimensional profile matching engine computing 0–100% fit scores, grades, colors, and matched skills for jobs, opps, and grants.
>   - [`services/copilot.py`](file:///services/copilot.py): 1-click tailored Cover Letter, Statement of Purpose, and Grant Pitch Proposal generator.
>   - [`ui/app.py`](file:///ui/app.py): FastAPI REST API and SPA server (`/api/opportunities`, `/api/jobs`, `/api/grants`, `/api/sources`, `/api/pipeline`, `/api/profile`, `/api/copilot/generate`, `/api/scrape/*`).
>   - [`ui/templates/index.html`](file:///ui/templates/index.html): Responsive Bento-Grid SPA with Candidate AI Profile modal, match pills, Spotlight AI Radar, 1-Click Copilot modal, 4-stage Kanban board, and multi-vertical filters.
>   - [`main.py`](file:///main.py): Argparse CLI entrypoint (`scrape`, `jobs`, `wwr`, `grants`, `sources`, `auto`, `ui`, `profile`, `match`, `copilot`).
> - **Current Status:** Milestone 12 backend, database, matching, copilot, CLI, and base UI completed. Scrapers Hub frontend rendering in `ui/templates/index.html` is the remaining task before Milestone 13.




