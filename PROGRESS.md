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
  - Interactive **Scrapers Control Hub (`#scrapers-view`)**: Live multi-vertical crawler grid connected to `/api/sources` with real-time status indicators, indexed counts, 1-click individual execution buttons (`Run Engine`), live millisecond execution toasts, and a direct URL/channel queuing input.

### Milestone 13: Free Mobile Alerts & Telegram Bot Dispatcher Engine
- **Location:** `services/telegram_bot.py`, `storage/db.py`, `ui/app.py`, `main.py`, `ui/templates/index.html`
- **Active Bot:** `@ScraperGaloreBot` (ID: `9278809224`, Token validated).
- **Architecture & Capabilities:**
  - Zero-cost mobile push alerts with rich HTML formatting, emoji classification, and match percentage ratings.
  - Interactive inline keyboard buttons (`[🔗 Direct Apply]`, `[⭐ Open Dashboard]`).
  - Auto Chat-ID Detection via `getUpdates` allowing 1-click pairing as soon as the user presses Start on `@ScraperGaloreBot`.
  - SQLite persistent settings table (`settings`) storing bot credentials, active chat targets, and preferences.
- **REST Endpoints (`ui/app.py`):**
  - `GET /api/telegram/status`: Validates bot credentials and active linked chat ID.
  - `POST /api/telegram/detect`: Polls `getUpdates` to auto-link the candidate's phone ID.
  - `POST /api/telegram/test`: Sends a rich verification test notification.
  - `POST /api/telegram/send`: Dispatches any selected scholarship, 4-day job, or grant to Telegram.
- **Frontend UI (`ui/templates/index.html`):**
  - Header pill showing live Telegram Bot connection state.
  - Dedicated **Telegram Alert Radar Modal** (`#telegram-modal`) with auto-detect and verification triggers.
  - Hero spotlight **"Push to Phone 📱"** button delivering instant cards.
- **CLI Commands (`main.py`):**
  - `uv run main.py notify`: View bot status and link.
  - `uv run main.py notify --detect`: Auto-detect and pair chat ID from incoming messages.
  - `uv run main.py notify --test`: Send test verification alert to Telegram.
  - `uv run main.py notify --type job --id <id>`: Dispatch specific job alert card.

### Milestone 14: Universal Feed Studio (Custom Source Onboarding)
- **Location:** `scrapers/universal_scraper.py`, `storage/db.py`, `ui/app.py`, `ui/templates/index.html`
- **Architecture & Capabilities:**
  - Zero-code custom feed onboarding: Add any RSS/Atom feed, public Telegram channel (`t.me/s/...`), or web page directly from the web interface.
  - Multi-category routing: Automatically routes parsed items into `opportunities`, `jobs`, or `grants` tables with deduplication and metadata extraction.
  - Database persistence: `custom_sources` table in SQLite tracking active sources, health, item counters, and last execution timestamps.
- **REST Endpoints (`ui/app.py`):**
  - `GET /api/custom-sources`: Returns all user-defined custom sources with status.
  - `POST /api/custom-sources`: Registers a new custom source with live URL uniqueness check.
  - `DELETE /api/custom-sources/{id}`: Removes a custom source.
  - `PATCH /api/custom-sources/{id}/toggle`: Pauses or activates a source.
  - `POST /api/scrape/custom/{id}`: Triggers an immediate scrape for a specific custom feed.
  - `POST /api/scrape/custom-all`: Concurrently syncs all active custom feeds.
- **Frontend UI (`ui/templates/index.html`):**
  - Glowing **"Feed Studio"** header button inside the Scrapers Control Hub.
  - Modal with quick-add form (name, URL, source type, target category) and live management list.
  - 1-Click execution, pause/resume toggle, and delete actions with instant execution toasts.

### Milestone 15: AI Resume Parser, Grade Extractor & Dynamic Recommendations Engine
- **Location:** `services/ai_resume.py`, `services/matcher.py`, `services/copilot.py`, `ui/app.py`, `ui/templates/index.html`, `main.py`
- **Architecture & Capabilities:**
  - Dual-Engine AI Architecture:
    1. **Free Cloud AI Tier**: Direct integration with Google Gemini Free Tier (`gemini-1.5-flash` / `gemini-2.0-flash`) via free API key for deep semantic parsing and cloud synthesis.
    2. **Built-in Free Heuristic AI Engine**: 100% offline, zero-network, zero-cost semantic NLP engine that extracts candidate credentials, GPA/academic honors, degrees, skills, and experience years.
  - Grade & Academic Merit Extractor:
    - Scans and detects GPA formats (`3.92 / 4.0`), Latin honors (`Magna Cum Laude`, `Summa Cum Laude`), UK honors (`First Class Honours`), class rank, and percentage scores.
    - Dynamically boosts fit scores for academic scholarships and prestigious fellowships based on verified academic standing.
  - Dynamic AI Recommendation System:
    - Evaluates candidate credentials against all active scholarships, 4-day remote jobs, and startup grants.
    - Generates personalized strategic summaries and custom "Why You Match" justifications.
  - Tailored Cover Letter & SOP Synthesis:
    - Automatically incorporates candidate's verified GPA, degree, and unique resume achievements directly into generated application documents.
- **REST Endpoints (`ui/app.py`):**
  - `GET /api/resume/status`: Checks calibrated resume state and active AI engine.
  - `POST /api/resume/upload`: Multi-part upload handler parsing `.pdf`, `.txt`, `.md` files.
  - `POST /api/resume/parse-text`: Direct raw resume text parsing endpoint.
  - `POST /api/resume/apply-to-profile`: Syncs extracted credentials into SQLite active user profile.
  - `GET /api/resume/recommendations`: Returns dynamic AI recommendations across all verticals.
  - `GET /api/settings/gemini-key` & `POST /api/settings/gemini-key`: Configure optional free Gemini API key.
- **Frontend UI (`ui/templates/index.html`):**
  - Dedicated **AI Resume Studio Modal** (`#resume-modal`) with drag-and-drop dropzone, text paste area, and dynamic recommendations tab.
  - Header badge displaying real-time calibrated academic standing (e.g. `3.92 GPA`).
  - Extracted credentials card review and 1-click sync to platform.
- **CLI Suite (`main.py`):**
  - `uv run main.py resume parse <file> [--save]`: Parse any resume and optionally sync to profile.
  - `uv run main.py resume recs`: Display personalized dynamic AI recommendations from terminal.

### Milestone 16: Complete Web Dashboard Redesign (SaaS Shell & Dual Grid/Table Views)
- **Location:** `ui/templates/index.html`
- **Architecture & Ergonomics:**
  - Replaced the initial 3-column / holographic mockup with a professional, responsive 2-column SaaS application layout (Linear / Stripe / Vercel style).
  - **Left Navigation Control Rail:** Fixed brand identity header with active server pulse, live KPI badges (Indexed opportunities, active pipeline applications), categorized stream links with counter badges, quick-launch buttons for AI Resume Studio, Scrapers Hub, and Pipeline Kanban, and candidate profile capsule.
  - **Top Workspace Toolbar:** Debounced universal search bar across all sources, multi-criteria sort selector (`Best Match`, `Closing Soonest`, `Salary / Funding`, `Recently Added`), dynamic **Card Grid** vs **Compact Table** view switcher, Telegram Phone Radar quick-launcher, live Sync button, and light/dark theme toggle.
  - **Executive Spotlight Banner:** Hero showcase highlighting the top AI-recommended opportunity with instant 1-click Copilot letter drafting, Telegram push, pipeline bookmarking, and official portal access.
  - **Dual Opportunity Display Modes:**
    - **Card Grid View:** Rich interactive cards with color-coded category pills, AI match percentage radar badges, salary/funding tags, deadline countdowns, and instant action buttons.
    - **Compact Table View:** High-density data grid optimized for rapid scanning with sortable columns for Title/Org, Category, Compensation/Funding, Deadline, Match Score, and Actions.
  - **Integrated Modals Suite:** 100% preservation of all live interactive modals (Candidate Profile Editor, 1-Click Application Copilot, AI Resume & Dynamic Recommendations Studio, Telegram Phone Radar, and Universal Feed Studio).
- **Standards & Best Practices:** Follows modern web design guidelines (`css-layout`, `responsive-design`, container queries, accessible contrast ratios, and dark/light color schemes).

---

## 4. Architectural Expansion Roadmap (Next Steps)

1. **Milestone 16: AI-Powered Semantic Search & Hybrid Vector Ranking:**
   - Integrate vector embeddings for natural-language query matching across listings.
2. **Milestone 17: User Authentication & Multi-Tenancy:**
   - Add FastAPI Auth (JWT or OAuth2 / GitHub login).
   - Per-user preferences: Saved search alerts, starred items in SQLite user table, and resume uploads.

---

## 5. How to Continue on Any Machine

When you open Antigravity on your other PC, follow these quick steps:

### 1. Pull Latest Changes
```bash
# Pull the latest commits including Milestones 13, 14 & 15
git pull origin main

# Ensure virtual environment and dependencies are up to date
uv sync
```

### 2. Populate Fresh Local Database (If needed)
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

# Parse your resume and calibrate AI profile:
uv run main.py resume parse sample_resume.txt --save

# View top dynamic recommendations:
uv run main.py resume recs

# Verify all sources:
uv run main.py sources
```

### 3. Launch the Bento Web Dashboard
```bash
uv run uvicorn ui.app:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://127.0.0.1:8000`** in your browser!

---

## 6. Antigravity Agent Briefing

> **Agent Context:**
> - **Project:** All-in-One Opportunity & Job Intelligence Platform ("ScraperGalore") with Dual Telegram/Web Crawlers, Interactive Bento-Grid SPA, 4-Stage Kanban Application Pipeline, Candidate AI Profile Matcher, 1-Click Application Copilot, Free Telegram Bot Alerts, Universal Feed Studio, and AI Resume & Recommendation Engine.
> - **Active Tech Stack:** Python 3.10+, `uv`, `httpx`, `beautifulsoup4`, `fastapi`, `uvicorn`, `sqlite3`, `pydantic`, `schedule`, `pypdf`, Tailwind CSS, FontAwesome.
> - **Architecture & Key Files:**
>   - [`services/ai_resume.py`](file:///services/ai_resume.py): Zero-cost AI resume parser (Gemini Free API + Offline Heuristic NLP), grade extractor, and dynamic recommendation engine.
>   - [`services/matcher.py`](file:///services/matcher.py): Multi-dimensional profile matching engine computing fit scores and academic merit bonuses.
>   - [`services/copilot.py`](file:///services/copilot.py): Tailored cover letter and statement of purpose generator with GPA and project weaving.
>   - [`scrapers/telegram_scraper.py`](file:///scrapers/telegram_scraper.py): Scrapes Telegram public channel previews (`https://t.me/s/...`) with zero credentials.
>   - [`scrapers/web_scraper.py`](file:///scrapers/web_scraper.py): Deep page scraper; cleans DOM, extracts key highlights (`<li>` bullets), and resolves CTA application URLs.
>   - [`scrapers/job_scraper.py`](file:///scrapers/job_scraper.py): Scrapes 50+ remote listings from `4dayweek.io/remote-jobs`.
>   - [`scrapers/wwr_scraper.py`](file:///scrapers/wwr_scraper.py): XML RSS scraper for WeWorkRemotely remote developer & devops listings.
>   - [`scrapers/grant_scraper.py`](file:///scrapers/grant_scraper.py): Tech Grants & Startup Accelerators indexer ($50k-$2.5M capital programs).
>   - [`scrapers/universal_scraper.py`](file:///scrapers/universal_scraper.py): Universal Feed Studio engine for custom user-defined RSS feeds, Telegram channels, and webpages.
>   - [`services/telegram_bot.py`](file:///services/telegram_bot.py): Telegram alert dispatcher linked to `@ScraperGaloreBot`.
>   - [`storage/db.py`](file:///storage/db.py): SQLite layer (`opportunities.db`) with `opportunities`, `jobs`, `grants`, `applications`, `user_profiles`, `settings`, and `custom_sources`.
>   - [`ui/app.py`](file:///ui/app.py): FastAPI REST API and SPA server.
>   - [`ui/templates/index.html`](file:///ui/templates/index.html): Responsive Bento-Grid SPA.
> - **Current Status:** Milestones 1 through 15 fully implemented, validated, and documented.






