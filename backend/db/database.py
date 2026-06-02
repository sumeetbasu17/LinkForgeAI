"""
SQLite database for posts, schedules, user preferences.
Uses SQLite for local dev, easily swappable to PostgreSQL for production.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from config.settings import settings


class Database:
    """SQLite-based storage for posts, preferences, and schedules."""

    def __init__(self, db_path: str = "linkedin_posts.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    format TEXT DEFAULT 'story',
                    tone TEXT DEFAULT 'Conversational',
                    status TEXT DEFAULT 'draft',
                    scheduled_date TEXT,
                    scheduled_time TEXT,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    reposts INTEGER DEFAULT 0,
                    impressions INTEGER DEFAULT 0,
                    research_data TEXT,
                    style_score REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY DEFAULT 'default',
                    active_categories TEXT DEFAULT '[]',
                    tone_overrides TEXT DEFAULT '{}',
                    default_tone TEXT DEFAULT 'Conversational',
                    default_format TEXT DEFAULT 'story',
                    posting_frequency INTEGER DEFAULT 3,
                    preferred_days TEXT DEFAULT '["Tue","Thu","Sat"]',
                    preferred_time TEXT DEFAULT '9:00 AM',
                    auto_post_enabled INTEGER DEFAULT 0,
                    style_profile TEXT DEFAULT '{}',
                    preferred_model TEXT DEFAULT '',
                    custom_rules TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS style_posts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    content TEXT NOT NULL,
                    post_type TEXT NOT NULL DEFAULT 'own',
                    category TEXT DEFAULT '',
                    source_url TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS linkedin_tokens (
                    user_id TEXT PRIMARY KEY DEFAULT 'default',
                    access_token TEXT NOT NULL,
                    refresh_token TEXT DEFAULT '',
                    expires_at TEXT NOT NULL,
                    linkedin_urn TEXT DEFAULT '',
                    linkedin_name TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
                CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
                CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category);
                CREATE INDEX IF NOT EXISTS idx_style_posts_user ON style_posts(user_id);
            """
            )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ─── Posts ────────────────────────────────────────────────────

    def create_post(
        self,
        post_id: str,
        title: str,
        content: str,
        category: str,
        user_id: str = "default",
        format: str = "story",
        tone: str = "Conversational",
        status: str = "draft",
        research_data: Optional[dict] = None,
        style_score: Optional[float] = None,
    ) -> dict:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO posts 
                   (id, user_id, title, content, category, format, tone, 
                    status, research_data, style_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    post_id, user_id, title, content, category, format, tone,
                    status, json.dumps(research_data) if research_data else None,
                    style_score, now, now,
                ),
            )
        return self.get_post(post_id)

    def get_post(self, post_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            return dict(row) if row else None

    def list_posts(
        self,
        user_id: str = "default",
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = "SELECT * FROM posts WHERE user_id = ?"
        params = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_post(self, post_id: str, **kwargs) -> Optional[dict]:
        if not kwargs:
            return self.get_post(post_id)

        kwargs["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [post_id]

        with self._conn() as conn:
            conn.execute(f"UPDATE posts SET {set_clause} WHERE id = ?", values)
        return self.get_post(post_id)

    def delete_post(self, post_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            return cursor.rowcount > 0

    def get_recent_post_titles(
        self, user_id: str = "default", limit: int = 20
    ) -> list[str]:
        """Get recent post titles to avoid topic repetition."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT title FROM posts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [r["title"] for r in rows]

    # ─── User Preferences ────────────────────────────────────────

    def get_preferences(self, user_id: str = "default") -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                prefs = dict(row)
                prefs["active_categories"] = json.loads(prefs.get("active_categories", "[]"))
                prefs["tone_overrides"] = json.loads(prefs.get("tone_overrides", "{}"))
                prefs["preferred_days"] = json.loads(prefs.get("preferred_days", "[]"))
                prefs["style_profile"] = json.loads(prefs.get("style_profile", "{}"))
                return prefs

            # Not found — create default and return it in the SAME connection
            now = datetime.now().isoformat()
            conn.execute(
                """INSERT INTO user_preferences (user_id, created_at, updated_at)
                   VALUES (?, ?, ?)""",
                (user_id, now, now),
            )
            # Return defaults directly instead of recursive call
            return {
                "user_id": user_id,
                "active_categories": [],
                "tone_overrides": {},
                "default_tone": "Conversational",
                "default_format": "story",
                "posting_frequency": 3,
                "preferred_days": ["Tue", "Thu", "Sat"],
                "preferred_time": "9:00 AM",
                "auto_post_enabled": 0,
                "style_profile": {},
                "preferred_model": "",
                "custom_rules": "",
                "created_at": now,
                "updated_at": now,
            }

    def update_preferences(self, user_id: str = "default", **kwargs) -> dict:
        # Ensure preferences exist
        self.get_preferences(user_id)

        # Serialize JSON fields
        json_fields = ["active_categories", "tone_overrides", "preferred_days", "style_profile"]
        for field in json_fields:
            if field in kwargs and not isinstance(kwargs[field], str):
                kwargs[field] = json.dumps(kwargs[field])

        kwargs["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]

        with self._conn() as conn:
            conn.execute(
                f"UPDATE user_preferences SET {set_clause} WHERE user_id = ?", values
            )
        return self.get_preferences(user_id)

    # ─── Style Posts ─────────────────────────────────────────────

    def add_style_post(
        self,
        post_id: str,
        content: str,
        post_type: str = "own",
        user_id: str = "default",
        category: str = "",
        source_url: str = "",
    ) -> dict:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO style_posts (id, user_id, content, post_type, category, source_url, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (post_id, user_id, content, post_type, category, source_url, now),
            )
        return {"id": post_id, "content": content, "post_type": post_type}

    def get_style_posts(
        self, user_id: str = "default", post_type: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        query = "SELECT * FROM style_posts WHERE user_id = ?"
        params = [user_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def delete_style_post(self, post_id: str) -> bool:
        """Delete a single style post."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM style_posts WHERE id = ?", (post_id,))
            return cursor.rowcount > 0

    def delete_style_posts_by_category(
        self, user_id: str = "default", category: str = "",
        post_type: Optional[str] = None,
    ) -> int:
        """Delete all style posts for a category. Returns count deleted."""
        query = "DELETE FROM style_posts WHERE user_id = ? AND category = ?"
        params = [user_id, category]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)

        with self._conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount

    def delete_all_style_posts(
        self, user_id: str = "default", post_type: Optional[str] = None,
    ) -> int:
        """Delete ALL style posts for a user. Returns count deleted."""
        query = "DELETE FROM style_posts WHERE user_id = ?"
        params = [user_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)

        with self._conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount

    def get_style_post_counts(self, user_id: str = "default") -> dict:
        """Get counts of style posts grouped by category and type."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT category, post_type, COUNT(*) as count 
                   FROM style_posts WHERE user_id = ? 
                   GROUP BY category, post_type""",
                (user_id,),
            ).fetchall()

            result = {"own": {}, "inspiration": {}, "comment": {}, "total_own": 0, "total_inspiration": 0, "total_comment": 0}
            for r in rows:
                r = dict(r)
                ptype = r["post_type"]
                cat = r["category"] or "uncategorized"
                count = r["count"]
                if ptype in result:
                    result[ptype][cat] = count
                    result[f"total_{ptype}"] = result.get(f"total_{ptype}", 0) + count
            return result

    # ─── LinkedIn Tokens ─────────────────────────────────────────

    def save_linkedin_token(
        self,
        access_token: str,
        refresh_token: str = "",
        expires_in: int = 5184000,
        linkedin_urn: str = "",
        linkedin_name: str = "",
        user_id: str = "default",
    ) -> dict:
        """Save or update LinkedIn OAuth tokens."""
        now = datetime.now()
        expires_at = (now + __import__('datetime').timedelta(seconds=expires_in)).isoformat()
        now_str = now.isoformat()

        with self._conn() as conn:
            # Upsert
            existing = conn.execute(
                "SELECT user_id FROM linkedin_tokens WHERE user_id = ?", (user_id,)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE linkedin_tokens 
                       SET access_token = ?, refresh_token = ?, expires_at = ?,
                           linkedin_urn = ?, linkedin_name = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (access_token, refresh_token, expires_at, linkedin_urn, linkedin_name, now_str, user_id),
                )
            else:
                conn.execute(
                    """INSERT INTO linkedin_tokens 
                       (user_id, access_token, refresh_token, expires_at, linkedin_urn, linkedin_name, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, access_token, refresh_token, expires_at, linkedin_urn, linkedin_name, now_str, now_str),
                )

        return {"access_token": access_token[:20] + "...", "expires_at": expires_at}

    def get_linkedin_token(self, user_id: str = "default") -> Optional[dict]:
        """Get stored LinkedIn token. Returns None if not found or expired."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM linkedin_tokens WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None

            token_data = dict(row)

            # Check if expired
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if datetime.now() > expires_at:
                token_data["expired"] = True
            else:
                token_data["expired"] = False
                days_left = (expires_at - datetime.now()).days
                token_data["days_remaining"] = days_left

            return token_data


# Singleton
database = Database()
