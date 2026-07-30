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
                    catch_up_minutes INTEGER DEFAULT 15,
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

                -- One row per scheduler tick. The scheduler only runs while the
                -- backend process is alive, so the *gaps* in this table are the
                -- evidence for "why didn't my 9:00 AM post go out at 9:00".
                CREATE TABLE IF NOT EXISTS scheduler_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    at TEXT NOT NULL,
                    action TEXT NOT NULL DEFAULT 'none',
                    reason TEXT DEFAULT '',
                    target_time TEXT DEFAULT '',
                    late_minutes INTEGER DEFAULT 0
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

                -- ─── Post images ──────────────────────────────────

                -- Who the generated card claims to be: real name and photo,
                -- plus how the badge is shown.
                CREATE TABLE IF NOT EXISTS image_identity (
                    user_id TEXT PRIMARY KEY DEFAULT 'default',
                    display_name TEXT DEFAULT '',
                    headline TEXT DEFAULT '',
                    avatar_path TEXT DEFAULT '',
                    verified INTEGER DEFAULT 0,
                    verified_color TEXT DEFAULT '#1D9BF0',
                    handle_strategy TEXT DEFAULT 'round-robin',
                    updated_at TEXT NOT NULL
                );

                -- Rotating pool of handles. use_count and last_used_at drive
                -- round-robin so the same handle doesn't repeat back to back.
                CREATE TABLE IF NOT EXISTS image_handles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    handle TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    use_count INTEGER DEFAULT 0,
                    last_used_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                -- Style extracted from an uploaded inspiration image, stored
                -- once and reused as a template preset.
                CREATE TABLE IF NOT EXISTS image_presets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT DEFAULT '',
                    archetype TEXT NOT NULL DEFAULT 'social-card',
                    style TEXT NOT NULL DEFAULT '{}',
                    source_image TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS post_images (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    post_id TEXT DEFAULT '',
                    archetype TEXT NOT NULL,
                    preset_id TEXT DEFAULT '',
                    handle TEXT DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
                CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
                CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category);
                CREATE INDEX IF NOT EXISTS idx_style_posts_user ON style_posts(user_id);
                CREATE INDEX IF NOT EXISTS idx_image_handles_user ON image_handles(user_id);
                CREATE INDEX IF NOT EXISTS idx_image_presets_user ON image_presets(user_id);
                CREATE INDEX IF NOT EXISTS idx_post_images_post ON post_images(post_id);
                CREATE INDEX IF NOT EXISTS idx_ticks_at ON scheduler_ticks(at);
            """
            )
        self._add_missing_columns()

    # Columns added after the first release. CREATE TABLE IF NOT EXISTS does
    # nothing to a database that already exists, so new columns are added here.
    _LATE_COLUMNS = {
        "user_preferences": {
            "preferred_model": "TEXT DEFAULT ''",
            "custom_rules": "TEXT DEFAULT ''",
            # Minutes after the preferred time during which a post may still be
            # published. Past it the post is saved as a draft instead of going
            # out hours late.
            "catch_up_minutes": "INTEGER DEFAULT 15",
        },
    }

    def _add_missing_columns(self):
        with self._conn() as conn:
            for table, columns in self._LATE_COLUMNS.items():
                existing = {
                    r["name"] for r in conn.execute(f"PRAGMA table_info({table})")
                }
                for name, ddl in columns.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

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

    def count_published_since(self, user_id: str, since_iso: str) -> int:
        """How many posts this user has published since a point in time.

        Backs the weekly cap, so autonomous mode can never post more than the
        user allowed however many days they selected.
        """
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS n FROM posts
                   WHERE user_id = ? AND status = 'published' AND created_at >= ?""",
                (user_id, since_iso),
            ).fetchone()
            return int(row["n"]) if row else 0

    def count_posts_today(
        self,
        user_id: str = "default",
        status: Optional[str] = None,
        id_prefix: Optional[str] = None,
        day: Optional[str] = None,
    ) -> int:
        """How many posts were created today, optionally by status or id prefix.

        The scheduler uses this twice: to avoid publishing twice in a day, and
        to avoid saving a fresh "missed the slot" draft on every 10-minute tick.
        """
        day = day or datetime.now().strftime("%Y-%m-%d")
        query = "SELECT COUNT(*) AS n FROM posts WHERE user_id = ? AND created_at LIKE ?"
        params: list = [user_id, f"{day}%"]
        if status:
            query += " AND status = ?"
            params.append(status)
        if id_prefix:
            query += " AND id LIKE ?"
            params.append(f"{id_prefix}%")
        with self._conn() as conn:
            row = conn.execute(query, params).fetchone()
            return int(row["n"]) if row else 0

    # ─── Scheduler ticks ─────────────────────────────────────────

    def record_scheduler_tick(
        self,
        user_id: str = "default",
        action: str = "none",
        reason: str = "",
        target_time: str = "",
        late_minutes: int = 0,
        keep: int = 500,
    ) -> None:
        """Log one scheduler evaluation, trimming old rows."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO scheduler_ticks
                   (user_id, at, action, reason, target_time, late_minutes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    datetime.now().isoformat(timespec="seconds"),
                    action,
                    reason,
                    target_time,
                    int(late_minutes),
                ),
            )
            conn.execute(
                """DELETE FROM scheduler_ticks WHERE id NOT IN
                   (SELECT id FROM scheduler_ticks ORDER BY id DESC LIMIT ?)""",
                (keep,),
            )

    def list_scheduler_ticks(self, user_id: str = "default", limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT at, action, reason, target_time, late_minutes
                   FROM scheduler_ticks WHERE user_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

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
                "catch_up_minutes": 15,
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

    def update_style_post_category(self, post_id: str, category: str) -> bool:
        """Set the category on an existing style post."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE style_posts SET category = ? WHERE id = ?",
                (category, post_id),
            )
            return cursor.rowcount > 0

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

    # ─── Image identity ──────────────────────────────────────────

    def get_image_identity(self, user_id: str = "default") -> dict:
        """Identity shown on generated cards. Creates a default row on first use."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM image_identity WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row:
                data = dict(row)
                data["verified"] = bool(data.get("verified"))
                return data

            now = datetime.now().isoformat()
            conn.execute(
                """INSERT INTO image_identity
                   (user_id, display_name, headline, avatar_path, verified,
                    verified_color, handle_strategy, updated_at)
                   VALUES (?, '', '', '', 0, '#1D9BF0', 'round-robin', ?)""",
                (user_id, now),
            )
            return {
                "user_id": user_id,
                "display_name": "",
                "headline": "",
                "avatar_path": "",
                "verified": False,
                "verified_color": "#1D9BF0",
                "handle_strategy": "round-robin",
                "updated_at": now,
            }

    def update_image_identity(self, user_id: str = "default", **fields) -> dict:
        """Update identity fields. Only known columns are written."""
        self.get_image_identity(user_id)  # ensure the row exists
        allowed = {
            "display_name",
            "headline",
            "avatar_path",
            "verified",
            "verified_color",
            "handle_strategy",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if updates:
            if "verified" in updates:
                updates["verified"] = 1 if updates["verified"] else 0
            sets = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [datetime.now().isoformat(), user_id]
            with self._conn() as conn:
                conn.execute(
                    f"UPDATE image_identity SET {sets}, updated_at = ? WHERE user_id = ?",
                    params,
                )
        return self.get_image_identity(user_id)

    # ─── Handle pool ─────────────────────────────────────────────

    def list_image_handles(self, user_id: str = "default") -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM image_handles WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["enabled"] = bool(d.get("enabled"))
                out.append(d)
            return out

    def add_image_handle(self, handle_id: str, handle: str, user_id: str = "default") -> dict:
        handle = handle.strip()
        if not handle.startswith("@"):
            handle = "@" + handle
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM image_handles WHERE user_id = ? AND handle = ?",
                (user_id, handle),
            ).fetchone()
            if existing:
                return {"id": existing["id"], "handle": handle, "duplicate": True}
            conn.execute(
                """INSERT INTO image_handles
                   (id, user_id, handle, enabled, use_count, last_used_at, created_at)
                   VALUES (?, ?, ?, 1, 0, '', ?)""",
                (handle_id, user_id, handle, datetime.now().isoformat()),
            )
        return {"id": handle_id, "handle": handle, "duplicate": False}

    def set_image_handle_enabled(self, handle_id: str, enabled: bool) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE image_handles SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, handle_id),
            )
            return cur.rowcount > 0

    def delete_image_handle(self, handle_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM image_handles WHERE id = ?", (handle_id,))
            return cur.rowcount > 0

    def pick_image_handle(self, user_id: str = "default", strategy: str = "round-robin") -> str:
        """Choose the next handle and record the use.

        Round-robin picks the least-used handle, breaking ties by the oldest
        last use, so a handle never repeats while others are still unused.
        """
        import random

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM image_handles WHERE user_id = ? AND enabled = 1",
                (user_id,),
            ).fetchall()
            if not rows:
                return ""

            handles = [dict(r) for r in rows]
            if strategy == "random":
                chosen = random.choice(handles)
            else:
                chosen = sorted(
                    handles,
                    key=lambda h: (h.get("use_count") or 0, h.get("last_used_at") or ""),
                )[0]

            conn.execute(
                "UPDATE image_handles SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
                (datetime.now().isoformat(), chosen["id"]),
            )
            return chosen["handle"]

    # ─── Style presets ───────────────────────────────────────────

    def add_image_preset(
        self,
        preset_id: str,
        archetype: str,
        style: dict,
        name: str = "",
        source_image: str = "",
        user_id: str = "default",
    ) -> dict:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO image_presets
                   (id, user_id, name, archetype, style, source_image, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    preset_id,
                    user_id,
                    name,
                    archetype,
                    json.dumps(style),
                    source_image,
                    datetime.now().isoformat(),
                ),
            )
        return {"id": preset_id, "archetype": archetype, "style": style}

    def list_image_presets(
        self, user_id: str = "default", archetype: Optional[str] = None
    ) -> list[dict]:
        query = "SELECT * FROM image_presets WHERE user_id = ?"
        params: list = [user_id]
        if archetype:
            query += " AND archetype = ?"
            params.append(archetype)
        query += " ORDER BY created_at DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        presets = []
        for r in rows:
            d = dict(r)
            d["enabled"] = bool(d.get("enabled"))
            try:
                d["style"] = json.loads(d.get("style") or "{}")
            except json.JSONDecodeError:
                d["style"] = {}
            presets.append(d)
        return presets

    def delete_image_preset(self, preset_id: str) -> Optional[dict]:
        """Delete a preset and return it, so the caller can clean up its file."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM image_presets WHERE id = ?", (preset_id,)
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM image_presets WHERE id = ?", (preset_id,))
            return dict(row)

    # ─── Generated images ────────────────────────────────────────

    def add_post_image(
        self,
        image_id: str,
        archetype: str,
        file_path: str,
        post_id: str = "",
        preset_id: str = "",
        handle: str = "",
        payload: Optional[dict] = None,
        user_id: str = "default",
    ) -> dict:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO post_images
                   (id, user_id, post_id, archetype, preset_id, handle, payload,
                    file_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    image_id,
                    user_id,
                    post_id,
                    archetype,
                    preset_id,
                    handle,
                    json.dumps(payload or {}),
                    file_path,
                    datetime.now().isoformat(),
                ),
            )
        return {"id": image_id, "archetype": archetype, "file_path": file_path}

    def get_post_images(self, post_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM post_images WHERE post_id = ? ORDER BY created_at DESC",
                (post_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.get("payload") or "{}")
            except json.JSONDecodeError:
                d["payload"] = {}
            out.append(d)
        return out

    def get_post_image(self, image_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM post_images WHERE id = ?", (image_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        return d

    def delete_post_image(self, image_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM post_images WHERE id = ?", (image_id,)
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM post_images WHERE id = ?", (image_id,))
            return dict(row)


# Singleton
database = Database()
