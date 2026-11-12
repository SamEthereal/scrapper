"""SQLite database layer for persisting and deduplicating opportunities."""

import json
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
            # Schema migration: Add deadline_date if upgrading an existing db
            columns = [col["name"] for col in conn.execute("PRAGMA table_info(opportunities);").fetchall()]
            if "deadline_date" not in columns:
                conn.execute("ALTER TABLE opportunities ADD COLUMN deadline_date TEXT;")

            # Indexes for fast search and sorting
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_title ON opportunities(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opp_deadline_date ON opportunities(deadline_date);")

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);")

            # Create applications table for Phase 4 (Application Tracker / Pipeline)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(item_type, item_id)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);")

            # Create user_profiles table for Milestone 11 (AI Matcher & Application Copilot)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    full_name TEXT NOT NULL,
                    email TEXT,
                    title TEXT,
                    skills TEXT NOT NULL,
                    degree TEXT,
                    experience_years INTEGER DEFAULT 0,
                    preferred_locations TEXT,
                    target_roles TEXT,
                    bio TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Seed default profile if none exists
            row = conn.execute("SELECT COUNT(*) FROM user_profiles;").fetchone()
            if row and row[0] == 0:
                conn.execute(
                    """
                    INSERT INTO user_profiles (
                        id, full_name, email, title, skills, degree, experience_years,
                        preferred_locations, target_roles, bio
                    ) VALUES (
                        1,
                        'Samuel Aseffa',
                        'sami.aseffa@gmail.com',
                        'Full-Stack & Distributed Systems Engineer',
                        'Python, FastAPI, TypeScript, React, Docker, Machine Learning, Data Scraping, SQL, Cloud Architecture',
                        'BSc in Computer Science',
                        4,
                        'Remote, Europe, North America',
                        'Software Engineer, Full-Stack Developer, AI Backend Engineer, Research Fellow',
                        'Passionate engineer specialized in scalable scrapers, intelligent automated pipelines, and modern web applications with 4+ years of hands-on experience.'
                    );
                    """
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

        with self._get_connection() as conn:
            cursor = conn.cursor()
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
                    is_opportunity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
            country: Specific country filter (e.g. 'UK', 'Spain', 'USA').
            level: Degree level (e.g. 'PhD', 'Master', 'Undergraduate').
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

        if country:
            conditions.append("(title LIKE ? OR key_highlights LIKE ?)")
            params.extend([f"%{country}%", f"%{country}%"])

        if level:
            conditions.append("(title LIKE ? OR key_highlights LIKE ?)")
            params.extend([f"%{level}%", f"%{level}%"])

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
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
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

    def get_pipeline(self) -> List[Dict[str, Any]]:
        """Returns all applications in the pipeline ordered by updated_at descending."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC;").fetchall()
            return [dict(r) for r in rows]

    def update_pipeline_item(
        self,
        app_id: int,
        status: Optional[str] = None,
        notes: Optional[str] = None,
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

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE applications SET {', '.join(updates)} WHERE id = ?;",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_pipeline_item(self, app_id: int) -> bool:
        """Deletes an application from the pipeline."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applications WHERE id = ?;", (app_id,))
            return cursor.rowcount > 0

    # =========================================================================
    # Milestone 11: User Profile Persistence (AI Matcher & Application Copilot)
    # =========================================================================

    def get_user_profile(self) -> Dict[str, Any]:
        """Retrieves the active user profile (id=1). Returns default if not yet created."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE id = 1;").fetchone()
            if not row:
                return {
                    "id": 1,
                    "full_name": "Samuel Aseffa",
                    "email": "sami.aseffa@gmail.com",
                    "title": "Full-Stack & Distributed Systems Engineer",
                    "skills": "Python, FastAPI, TypeScript, React, Docker, Machine Learning, Data Scraping, SQL, Cloud Architecture",
                    "skills_list": [
                        "Python", "FastAPI", "TypeScript", "React", "Docker",
                        "Machine Learning", "Data Scraping", "SQL", "Cloud Architecture"
                    ],
                    "degree": "BSc in Computer Science",
                    "experience_years": 4,
                    "preferred_locations": "Remote, Europe, North America",
                    "target_roles": "Software Engineer, Full-Stack Developer, AI Backend Engineer, Research Fellow",
                    "target_roles_list": [
                        "Software Engineer", "Full-Stack Developer", "AI Backend Engineer", "Research Fellow"
                    ],
                    "bio": "Passionate engineer specialized in scalable scrapers, intelligent automated pipelines, and modern web applications with 4+ years of hands-on experience.",
                    "updated_at": None,
                }
            data = dict(row)
            skills_raw = data.get("skills") or ""
            data["skills_list"] = [s.strip() for s in skills_raw.split(",") if s.strip()]
            roles_raw = data.get("target_roles") or ""
            data["target_roles_list"] = [r.strip() for r in roles_raw.split(",") if r.strip()]
            return data

    def save_user_profile(
        self,
        full_name: str,
        email: Optional[str] = None,
        title: Optional[str] = None,
        skills: str = "",
        degree: Optional[str] = None,
        experience_years: int = 0,
        preferred_locations: Optional[str] = None,
        target_roles: Optional[str] = None,
        bio: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upserts the active user profile (id=1) in the database."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (
                    id, full_name, email, title, skills, degree, experience_years,
                    preferred_locations, target_roles, bio, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    full_name = excluded.full_name,
                    email = excluded.email,
                    title = excluded.title,
                    skills = excluded.skills,
                    degree = excluded.degree,
                    experience_years = excluded.experience_years,
                    preferred_locations = excluded.preferred_locations,
                    target_roles = excluded.target_roles,
                    bio = excluded.bio,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (
                    full_name,
                    email or "",
                    title or "",
                    skills,
                    degree or "",
                    experience_years,
                    preferred_locations or "",
                    target_roles or "",
                    bio or "",
                ),
            )
            conn.commit()
            return self.get_user_profile()









  

            


        


    