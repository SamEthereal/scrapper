"""SQLite database layer for persisting and deduplicating opportunities."""

import json
import sqlite3
from typing import Any, Dict, List, Optional
from parsers.scholarship_parser import OpportunityItem


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

