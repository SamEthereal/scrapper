"""SQLite database layer for persisting and deduplicating opportunities."""

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional
from parsers.scholarship_parser import OpportunityItem
from parsers.job_parser import JobItem


class OpportunityDB:
    """Manages SQLite storage, deduplication, and retrieval of opportunities."""

    def __init__(self, db_path: str = "opportunities.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a connection with dictionary-like row access."""
        conn = sqlite3.connect(self.db_path)
        # sqlite3.Row allows accessing columns by name: row["title"]
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Creates the opportunities table and index if they don't exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_name TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    post_url TEXT,
                    date TEXT,
                    title TEXT NOT NULL,
                    deadline TEXT,
                    deadline_date TEXT,
                    apply_url TEXT,
                    official_portal TEXT,
                    key_highlights TEXT,
                    is_opportunity INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(channel_name, post_id)
                );
                """
            )
            # Schema migration: Add deadline_date, country, academic_level, funding_type if upgrading an existing db
            columns = [col["name"] for col in conn.execute("PRAGMA table_info(opportunities);").fetchall()]
            if "deadline_date" not in columns:
                conn.execute("ALTER TABLE opportunities ADD COLUMN deadline_date TEXT;")
            if "country" not in columns:
                conn.execute("ALTER TABLE opportunities ADD COLUMN country TEXT DEFAULT 'Global';")
            if "academic_level" not in columns:
                conn.execute("ALTER TABLE opportunities ADD COLUMN academic_level TEXT DEFAULT 'All Levels';")
            if "funding_type" not in columns:
                conn.execute("ALTER TABLE opportunities ADD COLUMN funding_type TEXT DEFAULT 'Fully Funded';")

            # Indexes for fast search and sorting
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_title ON opportunities(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_deadline_date ON opportunities(deadline_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_country ON opportunities(country);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_level ON opportunities(academic_level);")

            # Create jobs table for Phase 2
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    is_remote INTEGER DEFAULT 1,
                    salary TEXT,
                    schedule TEXT,
                    work_life_score INTEGER,
                    url TEXT UNIQUE,
                    source TEXT DEFAULT '4dayweek.io',
                    experience_level TEXT DEFAULT 'Mid-Level',
                    category TEXT DEFAULT 'IT & Software',
                    job_type TEXT DEFAULT 'Full-time',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Schema migration for jobs table
            job_cols = [col["name"] for col in conn.execute("PRAGMA table_info(jobs);").fetchall()]
            if "experience_level" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN experience_level TEXT DEFAULT 'Mid-Level';")
            if "category" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN category TEXT DEFAULT 'IT & Software';")
            if "job_type" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT DEFAULT 'Full-time';")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_exp ON jobs(experience_level);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_cat ON jobs(category);")

            # Create multi-tenant applications table (Application Tracker / Pipeline)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT '1',
                    item_type TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    subtitle TEXT,
                    deadline_or_salary TEXT,
                    deadline_date TEXT,
                    url TEXT,
                    status TEXT NOT NULL DEFAULT 'saved',
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, item_type, item_id)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_user ON applications(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(user_id, status);")

            # Create multi-tenant user_profiles table (AI Matcher, Copilot & Field Taxonomy)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE,
                    email TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    title TEXT,
                    field_of_study TEXT,
                    degree TEXT,
                    skills TEXT NOT NULL DEFAULT '',
                    experience_years INTEGER DEFAULT 0,
                    preferred_locations TEXT,
                    target_roles TEXT,
                    bio TEXT,
                    telegram_handle TEXT,
                    telegram_chat_id TEXT,
                    gpa_grades TEXT,
                    resume_raw TEXT,
                    extracted_data TEXT,
                    is_profile_complete INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);")

            # Create grants table for Milestone 12 (Tech Grants & Accelerators)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS grants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    funding_amount TEXT,
                    deadline TEXT,
                    deadline_date TEXT,
                    location TEXT DEFAULT 'Global / Remote',
                    stage TEXT DEFAULT 'Pre-Seed / Seed',
                    url TEXT UNIQUE,
                    key_highlights TEXT,
                    source TEXT DEFAULT 'Tech Grants & Accelerators',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_grants_title ON grants(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_grants_org ON grants(organization);")

            # Create settings table for Milestone 13 (Alerts, API Keys & System Config)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Create custom_sources table for Milestone 14 (Universal Feed Studio)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    items_count INTEGER DEFAULT 0,
                    last_scraped_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_csources_url ON custom_sources(url);")

            # Create users table for Phase 1 Authentication & 3-Persona Model
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    hashed_password TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    persona TEXT NOT NULL DEFAULT 'all',
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

            # Create crawl_history table for Autonomous Scheduling & Radar Audit metrics
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engine_id TEXT NOT NULL,
                    engine_name TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    duration_ms INTEGER DEFAULT 0,
                    items_scraped INTEGER DEFAULT 0,
                    new_inserted INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    error_message TEXT,
                    triggered_by TEXT DEFAULT 'autonomous'
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_history_started ON crawl_history(started_at DESC);")

            # Seed demo user if no users exist
            user_cnt = conn.execute("SELECT COUNT(*) FROM users;").fetchone()
            if user_cnt and user_cnt[0] == 0:
                demo_hash = "$2b$12$5xGdOR9PDlpczbM/O7Qwru8ns1RO30Wo155jRaC/DPj6BFWPmTEla"
                conn.execute(
                    """
                    INSERT INTO users (email, hashed_password, full_name, persona, role)
                    VALUES ('sami.aseffa@gmail.com', ?, 'Samuel Aseffa', 'all', 'admin');
                    """,
                    (demo_hash,),
                )

    def save_opportunity(
        self,
        item: OpportunityItem,
        official_portal: Optional[str] = None,
        key_highlights: Optional[List[str]] = None,
    ) -> bool:
        """
        Saves an opportunity to the database with deduplication.
        Returns True if newly inserted, False if already existed.
        """
        highlights_json = json.dumps(key_highlights or [], ensure_ascii=False)
        deadline_date = getattr(item, "deadline_date", None)

        country = getattr(item, "country", None) or "Global"
        academic_level = getattr(item, "academic_level", None) or "All Levels"
        funding_type = getattr(item, "funding_type", None) or "Fully Funded"

        # Multi-level Deduplication:
        # Check if an entry with the same non-generic apply_url, official_portal, or exact title already exists
        clean_title = re.sub(r"[^\w\s]", "", item.title.lower()).strip() if item.title else ""
        apply_url_clean = (item.apply_url or "").strip()
        is_generic_url = not apply_url_clean or apply_url_clean.rstrip("/").endswith("/opportunities") or len(apply_url_clean) < 15

        with self._get_connection() as conn:
            cursor = conn.cursor()

            existing = None
            if not is_generic_url:
                existing = cursor.execute(
                    "SELECT id, official_portal, deadline_date FROM opportunities WHERE apply_url = ?;",
                    (apply_url_clean,)
                ).fetchone()

            if not existing and official_portal and len(official_portal) > 15:
                existing = cursor.execute(
                    "SELECT id, official_portal, deadline_date FROM opportunities WHERE official_portal = ?;",
                    (official_portal,)
                ).fetchone()

            if not existing and clean_title and len(clean_title) > 8:
                existing = cursor.execute(
                    "SELECT id, official_portal, deadline_date FROM opportunities WHERE LOWER(TRIM(title)) = ?;",
                    (item.title.strip().lower(),)
                ).fetchone()

            if existing:
                # Merge enriched fields if available
                existing_id = existing["id"]
                updates = []
                u_params = []
                if official_portal and not existing["official_portal"]:
                    updates.append("official_portal = ?")
                    u_params.append(official_portal)
                if deadline_date and not existing["deadline_date"]:
                    updates.append("deadline_date = ?")
                    u_params.append(deadline_date)
                if updates:
                    u_params.append(existing_id)
                    cursor.execute(f"UPDATE opportunities SET {', '.join(updates)} WHERE id = ?;", tuple(u_params))
                return False  # Already exists, duplicate prevented!

            cursor.execute(
                """
                INSERT OR IGNORE INTO opportunities (
                    channel_name,
                    post_id,
                    post_url,
                    date,
                    title,
                    deadline,
                    deadline_date,
                    apply_url,
                    official_portal,
                    key_highlights,
                    is_opportunity,
                    country,
                    academic_level,
                    funding_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.channel_name,
                    item.post_id,
                    item.post_url,
                    item.date,
                    item.title,
                    item.deadline,
                    deadline_date,
                    item.apply_url,
                    official_portal,
                    highlights_json,
                    1 if item.is_opportunity else 0,
                    country,
                    academic_level,
                    funding_type,
                ),
            )
            return cursor.rowcount > 0

    def get_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves the most recent opportunities from the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM opportunities 
                ORDER BY id DESC 
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item_dict = dict(row)
                # Unpack JSON highlights into a Python list
                item_dict["key_highlights"] = json.loads(item_dict["key_highlights"] or "[]")
                results.append(item_dict)

            return results
    def filter_opportunities(
        self,
        keyword: Optional[str] = None,
        country: Optional[str] = None,
        level: Optional[str] = None,
        funding_type: Optional[str] = None,
        open_only: bool = False,
        has_deadline: bool = False,
        only_opportunities: bool = True,
        sort_by: str = "date",
        order: str = "DESC",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Dynamically filters and sorts opportunities using parameterized SQL.
        
        Args:
            keyword: Substring match across title and highlights.
            country: Specific country filter (e.g. 'Ethiopia', 'Germany', 'USA', 'UK').
            level: Degree level (e.g. 'PhD / Doctoral', "Master's", 'Undergraduate', 'Fellowship / Postdoc').
            funding_type: Funding scope (e.g. 'Fully Funded', 'Partial / Tuition', 'Research Grant / Stipend').
            open_only: If True, only returns opportunities whose deadline is today or in the future.
            has_deadline: If True, only returns opportunities with a known deadline.
            only_opportunities: If True, filters out ads/consultancy promos.
            sort_by: Column to sort by ('date', 'deadline', 'title', 'id').
            order: Sort direction ('ASC' or 'DESC').
            limit: Maximum records to return.
        """
        conditions = []
        params: List[Any] = []

        if only_opportunities:
            conditions.append("is_opportunity = 1")

        if keyword:
            conditions.append("(title LIKE ? OR key_highlights LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        if country and country.lower() != "all":
            conditions.append("(country = ? OR title LIKE ? OR key_highlights LIKE ?)")
            params.extend([country, f"%{country}%", f"%{country}%"])

        if level and level.lower() != "all":
            conditions.append("(academic_level = ? OR title LIKE ? OR key_highlights LIKE ?)")
            params.extend([level, f"%{level}%", f"%{level}%"])

        if funding_type and funding_type.lower() != "all":
            conditions.append("(funding_type = ? OR title LIKE ? OR key_highlights LIKE ?)")
            params.extend([funding_type, f"%{funding_type}%", f"%{funding_type}%"])

        if has_deadline:
            conditions.append("deadline_date IS NOT NULL AND deadline_date != ''")

        if open_only:
            # Matches records with future deadlines or open rolling deadlines
            conditions.append("(deadline_date IS NULL OR deadline_date >= date('now'))")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Safe sorting column mapping to prevent SQL injection
        sort_columns = {
            "date": "date",
            "deadline": "deadline_date",
            "title": "title",
            "id": "id",
        }
        sort_col = sort_columns.get(sort_by.lower(), "id")
        sort_direction = "ASC" if order.upper() == "ASC" else "DESC"

        # When sorting by deadline, push NULL/empty deadlines to the bottom
        if sort_col == "deadline_date":
            order_clause = f"ORDER BY CASE WHEN deadline_date IS NULL OR deadline_date = '' THEN 1 ELSE 0 END, deadline_date {sort_direction}"
        else:
            order_clause = f"ORDER BY {sort_col} {sort_direction}"

        sql = f"SELECT * FROM opportunities {where_clause} {order_clause} LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                item_dict = dict(row)
                item_dict["key_highlights"] = json.loads(item_dict["key_highlights"] or "[]")
                results.append(item_dict)

            return results

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """Searches opportunities matching a keyword in title or key highlights."""
        return self.filter_opportunities(keyword=keyword)

    def count(self) -> int:
        """Returns the total number of saved opportunities."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM opportunities;")
            return cursor.fetchone()[0]

    def get_closing_soon(self, days: int = 60) -> List[Dict[str, Any]]:
        """Returns opportunities closing within the next N days, sorted soonest first."""
        days_modifier = f"+{days} days"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM opportunities
                WHERE is_opportunity = 1
                  AND deadline_date >= date('now')
                  AND deadline_date <= date('now', ?)
                ORDER BY deadline_date ASC;
                """,
                (days_modifier,),
            )

            rows = cursor.fetchall()
            results = []

            for row in rows:
                item_dict = dict(row)
                item_dict["key_highlights"] = json.loads(item_dict["key_highlights"] or "[]")
                results.append(item_dict)

            return results

    # ==========================================
    # JOB BOARD PERSISTENCE & QUERIES (PHASE 2)
    # ==========================================

    def save_job(self, job: JobItem) -> bool:
        """
        Saves a job listing to the database with deduplication on URL.
        Returns True if newly inserted, False if already exists.
        """
        exp_level = getattr(job, "experience_level", None) or "Mid-Level"
        cat = getattr(job, "category", None) or "IT & Software"
        jtype = getattr(job, "job_type", None) or "Full-time"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    title,
                    company,
                    location,
                    is_remote,
                    salary,
                    schedule,
                    work_life_score,
                    url,
                    source,
                    experience_level,
                    category,
                    job_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.title,
                    job.company,
                    job.location,
                    1 if job.is_remote else 0,
                    job.salary,
                    job.schedule,
                    job.work_life_score,
                    job.url,
                    job.source,
                    exp_level,
                    cat,
                    jtype,
                ),
            )
            return cursor.rowcount > 0

    def count_jobs(self) -> int:
        """Returns the total number of saved job listings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs;")
            return cursor.fetchone()[0]

    def get_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recently saved jobs."""
        return self.filter_jobs(limit=limit)

    def search_jobs(self, keyword: str) -> List[Dict[str, Any]]:
        """Searches jobs by title, company, or location."""
        return self.filter_jobs(keyword=keyword)

    def filter_jobs(
        self,
        keyword: Optional[str] = None,
        company: Optional[str] = None,
        experience_level: Optional[str] = None,
        category: Optional[str] = None,
        job_type: Optional[str] = None,
        has_salary: bool = False,
        remote_only: bool = False,
        min_score: Optional[int] = None,
        sort_by: str = "id",
        order: str = "DESC",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Dynamically filters and sorts job listings.
        """
        conditions = []
        params: List[Any] = []

        if keyword:
            conditions.append("(title LIKE ? OR company LIKE ? OR location LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        if company:
            conditions.append("company LIKE ?")
            params.append(f"%{company}%")

        if experience_level and experience_level.lower() != "all":
            conditions.append("experience_level = ?")
            params.append(experience_level)

        if category and category.lower() != "all":
            conditions.append("category = ?")
            params.append(category)

        if job_type and job_type.lower() != "all":
            conditions.append("job_type = ?")
            params.append(job_type)

        if has_salary:
            conditions.append("salary IS NOT NULL AND salary != ''")

        if remote_only:
            conditions.append("is_remote = 1")

        if min_score is not None:
            conditions.append("work_life_score >= ?")
            params.append(min_score)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sort_columns = {
            "id": "id",
            "title": "title",
            "company": "company",
            "score": "work_life_score",
        }
        sort_col = sort_columns.get(sort_by.lower(), "id")
        sort_direction = "ASC" if order.upper() == "ASC" else "DESC"

        # Push NULL work-life scores to bottom if sorting by score
        if sort_col == "work_life_score":
            order_clause = f"ORDER BY CASE WHEN work_life_score IS NULL THEN 1 ELSE 0 END, work_life_score {sort_direction}"
        else:
            order_clause = f"ORDER BY {sort_col} {sort_direction}"

        sql = f"SELECT * FROM jobs {where_clause} {order_clause} LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_opportunity_by_id(self, opp_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single opportunity by its database ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM opportunities WHERE id = ?;", (opp_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["key_highlights"] = json.loads(res["key_highlights"] or "[]")
            return res

    def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single job listing by its database ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?;", (job_id,)).fetchone()
            return dict(row) if row else None

    def add_to_pipeline(
        self,
        item_type: str,
        item_id: int,
        title: str,
        subtitle: Optional[str] = None,
        deadline_or_salary: Optional[str] = None,
        deadline_date: Optional[str] = None,
        url: Optional[str] = None,
        status: str = "saved",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Adds or updates an application entry in the pipeline."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO applications (
                    item_type, item_id, title, subtitle, deadline_or_salary,
                    deadline_date, url, status, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_type, item_id) DO UPDATE SET
                    status = excluded.status,
                    notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE applications.notes END,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (item_type, item_id, title, subtitle, deadline_or_salary, deadline_date, url, status, notes),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM applications WHERE item_type = ? AND item_id = ?;",
                (item_type, item_id),
            ).fetchone()
            return dict(row)

    def add_to_pipeline(
        self,
        item_type: str,
        item_id: int,
        title: str,
        subtitle: Optional[str] = None,
        deadline_or_salary: Optional[str] = None,
        deadline_date: Optional[str] = None,
        url: Optional[str] = None,
        status: str = "saved",
        notes: str = "",
        user_id: str = "1",
    ) -> Dict[str, Any]:
        """Adds or updates an application in the user's pipeline with atomic conflict resolution."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO applications (
                    user_id, item_type, item_id, title, subtitle, deadline_or_salary,
                    deadline_date, url, status, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, item_type, item_id) DO UPDATE SET
                    status = excluded.status,
                    notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE applications.notes END,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, item_type, item_id, title, subtitle, deadline_or_salary, deadline_date, url, status, notes),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM applications WHERE user_id = ? AND item_type = ? AND item_id = ?;",
                (user_id, item_type, item_id),
            ).fetchone()
            return dict(row)

    def get_pipeline(self, user_id: str = "1") -> List[Dict[str, Any]]:
        """Returns all applications in the pipeline for the given user, ordered by updated_at descending."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY updated_at DESC;", (str(user_id),)).fetchall()
            return [dict(r) for r in rows]

    def update_pipeline_item(
        self,
        app_id: int,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Updates the status and/or notes of an application in the pipeline."""
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        params.append(app_id)

        sql = f"UPDATE applications SET {', '.join(updates)} WHERE id = ?"
        if user_id:
            sql += " AND user_id = ?"
            params.append(str(user_id))

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql + ";", tuple(params))
            return cursor.rowcount > 0

    def delete_pipeline_item(self, app_id: int, user_id: Optional[str] = None) -> bool:
        """Deletes an application from the pipeline."""
        sql = "DELETE FROM applications WHERE id = ?"
        params = [app_id]
        if user_id:
            sql += " AND user_id = ?"
            params.append(str(user_id))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql + ";", tuple(params))
            return cursor.rowcount > 0

    # =========================================================================
    # Milestone 11: Multi-User Profile Persistence & AI Matcher
    # =========================================================================

    def get_user_profile(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves a specific user's profile. If not yet created, returns a template pre-filled with auth info."""
        with self._get_connection() as conn:
            row = None
            if user_id or email:
                u_str = str(user_id) if user_id is not None else ""
                e_str = email.strip().lower() if email else ""
                row = conn.execute(
                    """
                    SELECT * FROM user_profiles
                    WHERE (user_id = ? AND ? != '') OR (email = ? AND ? != '')
                    LIMIT 1;
                    """,
                    (u_str, u_str, e_str, e_str),
                ).fetchone()

            # If no specific user requested or not found by specific credentials, check for any default profile
            if not row and not user_id and not email:
                row = conn.execute("SELECT * FROM user_profiles ORDER BY id ASC LIMIT 1;").fetchone()

            if not row:
                # Check if user exists in `users` table to pre-fill their auth details
                auth_user = None
                if user_id or email:
                    u_str = str(user_id) if user_id is not None else ""
                    e_str = email.strip().lower() if email else ""
                    auth_user = conn.execute(
                        "SELECT * FROM users WHERE (id = ? AND ? != '') OR (email = ? AND ? != '') LIMIT 1;",
                        (u_str, u_str, e_str, e_str),
                    ).fetchone()

                name = auth_user["full_name"] if auth_user else "Applicant"
                em = auth_user["email"] if auth_user else (email or "")
                uid = str(auth_user["id"]) if auth_user else (str(user_id) if user_id else None)

                return {
                    "id": None,
                    "user_id": uid,
                    "full_name": name,
                    "email": em,
                    "title": "",
                    "field_of_study": "",
                    "degree": "",
                    "skills": "",
                    "skills_list": [],
                    "experience_years": 0,
                    "preferred_locations": "Remote",
                    "target_roles": "",
                    "target_roles_list": [],
                    "bio": "",
                    "telegram_handle": "",
                    "telegram_chat_id": "",
                    "gpa_grades": "",
                    "resume_raw": None,
                    "extracted_data": None,
                    "is_profile_complete": False,
                    "updated_at": None,
                }

            data = dict(row)
            skills_raw = data.get("skills") or ""
            data["skills_list"] = [s.strip() for s in skills_raw.split(",") if s.strip()]
            roles_raw = data.get("target_roles") or ""
            data["target_roles_list"] = [r.strip() for r in roles_raw.split(",") if r.strip()]
            data["is_profile_complete"] = bool(data.get("is_profile_complete", 0))
            if not data.get("gpa_grades"):
                data["gpa_grades"] = "3.85 / 4.0 (First Class Honours)"
            return data

    def save_user_profile(
        self,
        full_name: str,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        field_of_study: Optional[str] = None,
        degree: Optional[str] = None,
        skills: str = "",
        experience_years: int = 0,
        preferred_locations: Optional[str] = None,
        target_roles: Optional[str] = None,
        bio: Optional[str] = None,
        telegram_handle: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        gpa_grades: Optional[str] = None,
        resume_raw: Optional[str] = None,
        extracted_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upserts a specific user profile in the database keyed by email or user_id."""
        clean_email = email.strip().lower() if email else None
        clean_uid = str(user_id) if user_id is not None else None

        with self._get_connection() as conn:
            # Check if this profile already exists
            existing = None
            if clean_email or clean_uid:
                e_val = clean_email or ""
                u_val = clean_uid or ""
                existing = conn.execute(
                    "SELECT id, user_id, email FROM user_profiles WHERE (email = ? AND ? != '') OR (user_id = ? AND ? != '') LIMIT 1;",
                    (e_val, e_val, u_val, u_val),
                ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE user_profiles SET
                        full_name = ?,
                        email = COALESCE(?, email),
                        user_id = COALESCE(?, user_id),
                        title = ?,
                        field_of_study = ?,
                        degree = ?,
                        skills = ?,
                        experience_years = ?,
                        preferred_locations = ?,
                        target_roles = ?,
                        bio = ?,
                        telegram_handle = COALESCE(?, telegram_handle),
                        telegram_chat_id = COALESCE(?, telegram_chat_id),
                        gpa_grades = COALESCE(?, gpa_grades),
                        resume_raw = COALESCE(?, resume_raw),
                        extracted_data = COALESCE(?, extracted_data),
                        is_profile_complete = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (
                        full_name,
                        clean_email,
                        clean_uid,
                        title or "",
                        field_of_study or "",
                        degree or "",
                        skills,
                        experience_years,
                        preferred_locations or "",
                        target_roles or "",
                        bio or "",
                        telegram_handle,
                        telegram_chat_id,
                        gpa_grades,
                        resume_raw,
                        extracted_data,
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id, email, full_name, title, field_of_study, degree, skills,
                        experience_years, preferred_locations, target_roles, bio,
                        telegram_handle, telegram_chat_id, gpa_grades, resume_raw,
                        extracted_data, is_profile_complete, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP);
                    """,
                    (
                        clean_uid,
                        clean_email,
                        full_name,
                        title or "",
                        field_of_study or "",
                        degree or "",
                        skills,
                        experience_years,
                        preferred_locations or "",
                        target_roles or "",
                        bio or "",
                        telegram_handle or "",
                        telegram_chat_id or "",
                        gpa_grades or "",
                        resume_raw,
                        extracted_data,
                    ),
                )
            conn.commit()
            return self.get_user_profile(user_id=clean_uid, email=clean_email)

    def update_resume_data(
        self,
        resume_raw: str,
        extracted: Dict[str, Any],
        gpa_grades: Optional[str] = None,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates user profile directly from parsed resume data."""
        import json
        full_name = extracted.get("full_name") or "Applicant"
        user_email = email or extracted.get("email")
        title = extracted.get("title")
        skills = extracted.get("skills") or ""
        degree = extracted.get("degree")
        field_of_study = extracted.get("field_of_study") or extracted.get("major")
        experience_years = int(extracted.get("experience_years") or 0)
        target_roles = extracted.get("target_roles")
        bio = extracted.get("bio")
        gpa = gpa_grades or extracted.get("gpa_grades")

        extracted_str = json.dumps(extracted, ensure_ascii=False)
        return self.save_user_profile(
            full_name=full_name,
            email=user_email,
            user_id=user_id,
            title=title,
            field_of_study=field_of_study,
            degree=degree,
            skills=skills,
            experience_years=experience_years,
            target_roles=target_roles,
            bio=bio,
            gpa_grades=gpa,
            resume_raw=resume_raw,
            extracted_data=extracted_str,
        )

    # =========================================================================
    # Milestone 12: Tech Grants & Accelerators Storage
    # =========================================================================

    def save_grant(self, grant: Any) -> bool:
        """
        Saves a Tech Grant or Accelerator item into SQLite with URL deduplication.
        Returns True if a new record was inserted, False if skipped.
        """
        if hasattr(grant, "title"):
            title = grant.title
            org = grant.organization
            funding = grant.funding_amount
            deadline = grant.deadline
            deadline_date = grant.deadline_date
            location = grant.location
            stage = grant.stage
            url = grant.url
            highlights = getattr(grant, "key_highlights", [])
            source = getattr(grant, "source", "Tech Grants & Accelerators")
        else:
            title = grant.get("title")
            org = grant.get("organization")
            funding = grant.get("funding_amount")
            deadline = grant.get("deadline")
            deadline_date = grant.get("deadline_date")
            location = grant.get("location", "Global / Remote")
            stage = grant.get("stage", "Pre-Seed / Seed")
            url = grant.get("url")
            highlights = grant.get("key_highlights", [])
            source = grant.get("source", "Tech Grants & Accelerators")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO grants (
                    title, organization, funding_amount, deadline, deadline_date,
                    location, stage, url, key_highlights, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    title,
                    org,
                    funding,
                    deadline,
                    deadline_date,
                    location,
                    stage,
                    url,
                    json.dumps(highlights),
                    source,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_grants(self, limit: int = 50, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves tech grants and accelerators with optional keyword search."""
        query = "SELECT * FROM grants"
        params = []
        if keyword:
            query += " WHERE title LIKE ? OR organization LIKE ? OR stage LIKE ?"
            param = f"%{keyword}%"
            params.extend([param, param, param])
        query += " ORDER BY id DESC LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("key_highlights"):
                    try:
                        item["key_highlights"] = json.loads(item["key_highlights"])
                    except Exception:
                        item["key_highlights"] = []
                else:
                    item["key_highlights"] = []
                results.append(item)
            return results

    def get_grant_by_id(self, grant_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single grant by its database ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM grants WHERE id = ?;", (grant_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            if item.get("key_highlights"):
                try:
                    item["key_highlights"] = json.loads(item["key_highlights"])
                except Exception:
                    item["key_highlights"] = []
            return item

    def count_grants(self) -> int:
        """Returns total number of stored grants & accelerators."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM grants;").fetchone()
            return row[0] if row else 0

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieves a configuration value from SQLite."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Stores or updates a configuration value in SQLite."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value),
            )
            conn.commit()

    def get_all_settings(self) -> Dict[str, str]:
        """Returns all configured settings as a key-value dictionary."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM settings;").fetchall()
            return {r["key"]: r["value"] for r in rows}

    # =========================================================================
    # Milestone 14: Universal Feed Studio — Custom Sources CRUD
    # =========================================================================

    def add_custom_source(
        self, name: str, url: str, source_type: str, category: str
    ) -> Dict[str, Any]:
        """Adds a new custom scraping source. Returns the created record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO custom_sources (name, url, source_type, category)
                VALUES (?, ?, ?, ?);
                """,
                (name, url, source_type, category),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM custom_sources WHERE id = ?;", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)

    def get_custom_sources(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Returns all custom sources, optionally filtered to active ones."""
        query = "SELECT * FROM custom_sources"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at DESC;"
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]

    def delete_custom_source(self, source_id: int) -> bool:
        """Deletes a custom source by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM custom_sources WHERE id = ?;", (source_id,))
            return cursor.rowcount > 0

    def toggle_custom_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Toggles a custom source between active/inactive. Returns updated record."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM custom_sources WHERE id = ?;", (source_id,)
            ).fetchone()
            if not row:
                return None
            new_active = 0 if row["is_active"] else 1
            conn.execute(
                "UPDATE custom_sources SET is_active = ? WHERE id = ?;",
                (new_active, source_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM custom_sources WHERE id = ?;", (source_id,)
            ).fetchone()
            return dict(updated)

    def update_custom_source_stats(self, source_id: int, items_count: int) -> None:
        """Updates the items_count and last_scraped_at for a custom source."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE custom_sources SET items_count = ?, last_scraped_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (items_count, source_id),
            )
            conn.commit()

    # =========================================================================
    # Phase 1: Authentication & User Accounts (3-Persona Model)
    # =========================================================================

    def create_user(
        self,
        email: str,
        hashed_password: str,
        full_name: str,
        persona: str = "all",
        role: str = "user",
    ) -> Dict[str, Any]:
        """Creates a new user record. Returns dictionary representation of the user."""
        email_clean = email.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (email, hashed_password, full_name, persona, role)
                VALUES (?, ?, ?, ?, ?);
                """,
                (email_clean, hashed_password, full_name.strip(), persona, role),
            )
            user_id = cursor.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
            user_dict = dict(row)
            user_dict.pop("hashed_password", None)
            return user_dict

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user by email address, including hashed_password for validation."""
        if not email:
            return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?;",
                (email.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a user by ID without returning hashed_password."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, full_name, persona, role, created_at, last_login FROM users WHERE id = ?;",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_user_persona(self, user_id: int, persona: str) -> bool:
        """Updates the user's active persona preference ('student', 'job_seeker', 'all')."""
        valid_personas = {"student", "job_seeker", "all"}
        if persona not in valid_personas:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET persona = ? WHERE id = ?;",
                (persona, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_user_last_login(self, user_id: int) -> bool:
        """Updates the last_login timestamp for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?;",
                (user_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Option 2: Autonomous Scheduler & Crawl Audit History
    # =========================================================================

    def log_crawl(
        self,
        engine_id: str,
        engine_name: str,
        started_at: str,
        completed_at: str,
        duration_ms: int,
        items_scraped: int,
        new_inserted: int,
        status: str = "success",
        error_message: Optional[str] = None,
        triggered_by: str = "autonomous",
    ) -> int:
        """Logs a single crawler execution into crawl_history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO crawl_history (
                    engine_id, engine_name, started_at, completed_at,
                    duration_ms, items_scraped, new_inserted, status,
                    error_message, triggered_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    engine_id,
                    engine_name,
                    started_at,
                    completed_at,
                    duration_ms,
                    items_scraped,
                    new_inserted,
                    status,
                    error_message,
                    triggered_by,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_crawl_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent crawler execution history sorted newest first."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM crawl_history ORDER BY started_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_crawl_stats(self) -> Dict[str, Any]:
        """Returns summary metrics of autonomous crawling performance."""
        with self._get_connection() as conn:
            total_runs_row = conn.execute("SELECT COUNT(*) FROM crawl_history;").fetchone()
            total_runs = total_runs_row[0] if total_runs_row else 0

            successful_runs_row = conn.execute("SELECT COUNT(*) FROM crawl_history WHERE status = 'success';").fetchone()
            successful_runs = successful_runs_row[0] if successful_runs_row else 0

            total_new_row = conn.execute("SELECT COALESCE(SUM(new_inserted), 0) FROM crawl_history;").fetchone()
            total_new = total_new_row[0] if total_new_row else 0

            last_run_row = conn.execute("SELECT * FROM crawl_history ORDER BY started_at DESC LIMIT 1;").fetchone()
            last_run = dict(last_run_row) if last_run_row else None

            success_rate = round((successful_runs / total_runs * 100), 1) if total_runs > 0 else 100.0

            return {
                "total_runs": total_runs,
                "successful_runs": successful_runs,
                "failed_runs": total_runs - successful_runs,
                "success_rate": success_rate,
                "total_new_discovered": total_new,
                "last_run": last_run,
            }

    def get_recent_new_items(self, since_iso: str) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieves opportunities, jobs, and grants created since a given ISO timestamp."""
        with self._get_connection() as conn:
            opps = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM opportunities WHERE created_at >= ? ORDER BY id DESC;",
                    (since_iso,),
                ).fetchall()
            ]
            jobs = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM jobs WHERE created_at >= ? ORDER BY id DESC;",
                    (since_iso,),
                ).fetchall()
            ]
            grants = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM grants WHERE created_at >= ? ORDER BY id DESC;",
                    (since_iso,),
                ).fetchall()
            ]
            return {"opportunities": opps, "jobs": jobs, "grants": grants}
