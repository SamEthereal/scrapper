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

---

## 4. Architectural Expansion Roadmap (Using the Full Might of Scraping)

1. **Additional Data Verticals (Scraper Expansion):**
   - **Tech Grants & Startup Accelerators:** Y-Combinator, Techstars, EU Horizon grants, AI research compute credits.
   - **Remote Freelance & High-Ticket Gigs:** WeWorkRemotely, Hacker News "Who is hiring?", Upwork RSS feeds.
   - **Tech News & Release Radar:** Scraping AI release feeds, arXiv paper drops, and GitHub trending repos.
2. **User Authentication & Multi-Tenancy:**
   - Add FastAPI Auth (JWT or OAuth2 / GitHub login).
   - Per-user preferences: Saved search alerts, starred items in PostgreSQL/SQLite user table, and resume uploads.
3. **AI Semantic Matching & Auto-Summary:**
   - Embed opportunities with vector embeddings or use an LLM to compare a user's resume against listings and output a Match Score (e.g. 94% fit).
   - Auto-generate customized cover letters tailored to the scraped requirements.
4. **Push Distribution Channels:**
   - Automated Telegram bot dispatching instant push alerts to private user channels.
   - Weekly automated digest newsletter generated via email.

---

## 5. How to Continue on Another PC

When you clone this repo on your work PC:
1. Clone the repository:
   ```bash
   git clone https://github.com/SamEthereal/scrapper.git
   cd scrapper
   ```
2. Run `uv sync` to install dependencies into the virtual environment automatically.
3. Launch the web dashboard:
   ```bash
   uv run main.py ui
   ```
4. Open Antigravity in that folder and start a new chat with:
   > *"I've pulled the repo on my work PC. Read PROGRESS.md and let's continue where we left off."*


