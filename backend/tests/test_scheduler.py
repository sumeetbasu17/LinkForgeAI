"""Tests for the scheduler's publish / draft / skip decision.

Run with:  python backend/tests/test_scheduler.py
      or:  pytest backend/tests/test_scheduler.py
"""

import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Point the database at a throwaway file before anything imports the singleton.
import db.database as db_module  # noqa: E402

_tmp = tempfile.mkdtemp()
db_module.database = db_module.Database(os.path.join(_tmp, "test.db"))

from services import scheduler  # noqa: E402

scheduler.database = db_module.database

WED_9AM = datetime(2026, 7, 29, 9, 0)


def _prefs(**over):
    base = {
        "user_id": "default",
        "auto_post_enabled": 1,
        "active_categories": ["ai-engineering"],
        "preferred_days": ["Mon", "Wed", "Fri"],
        "preferred_time": "9:00 AM",
        "posting_frequency": 3,
        "catch_up_minutes": 15,
    }
    base.update(over)
    return base


def test_publishes_inside_the_window():
    for minute in (0, 9, 15):
        at = WED_9AM.replace(minute=minute)
        assert scheduler.evaluate(_prefs(), at)["action"] == "publish", minute


def test_drafts_once_the_window_has_passed():
    """The 11:29 case: too late to publish, so write a draft instead."""
    decision = scheduler.evaluate(_prefs(), datetime(2026, 7, 29, 11, 29))
    assert decision["action"] == "draft"
    assert decision["late_minutes"] == 149
    assert "Missed the 9:00 AM slot" in decision["reason"]


def test_too_early_does_nothing():
    decision = scheduler.evaluate(_prefs(), datetime(2026, 7, 29, 8, 45))
    assert decision["action"] == "none"
    assert "Too early" in decision["reason"]


def test_wrong_day_does_nothing():
    # 2026-07-28 is a Tuesday, which is not in the preferred days.
    decision = scheduler.evaluate(_prefs(), datetime(2026, 7, 28, 9, 5))
    assert decision["action"] == "none"
    assert "not a selected day" in decision["reason"]


def test_autonomous_off_does_nothing():
    decision = scheduler.evaluate(_prefs(auto_post_enabled=0), WED_9AM)
    assert decision["action"] == "none"


def test_window_is_configurable():
    # A Monday, so it is a preferred day and carries no draft from other tests.
    late = datetime(2026, 7, 27, 11, 29)
    assert scheduler.evaluate(_prefs(catch_up_minutes=240), late)["action"] == "publish"
    assert scheduler.evaluate(_prefs(catch_up_minutes=15), late)["action"] == "draft"


def test_second_draft_is_not_written_the_same_day():
    """A 10-minute tick must not produce a draft every tick after the slot."""
    day = "2026-07-29"
    db_module.database.create_post(
        post_id="auto_testdraft01",
        title="Missed slot draft",
        content="body",
        category="ai-engineering",
        status="draft",
    )
    with db_module.database._conn() as conn:
        conn.execute(
            "UPDATE posts SET created_at = ? WHERE id = 'auto_testdraft01'",
            (f"{day}T11:29:00",),
        )
    decision = scheduler.evaluate(_prefs(), datetime(2026, 7, 29, 11, 39))
    assert decision["action"] == "none"
    assert "already saved" in decision["reason"]


def test_slot_job_fires_at_the_exact_configured_time():
    """A 9:00 AM slot must be a cron job at 9:00, not a 10-minute sweep."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("SKIP  apscheduler not installed")
        return

    db_module.database.update_preferences(
        "default", preferred_days=["Mon", "Wed", "Fri"], preferred_time="9:00 AM"
    )
    scheduler._scheduler = BackgroundScheduler()
    try:
        result = scheduler.sync_slot_job("default")
        assert result["scheduled"] is True, result
        job = scheduler._scheduler.get_job(scheduler.SLOT_JOB_ID)
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["hour"] == "9", fields
        assert fields["minute"] == "0", fields
        assert set(fields["day_of_week"].split(",")) == {"mon", "wed", "fri"}, fields
    finally:
        scheduler._scheduler = None


def test_slot_job_is_removed_when_no_days_are_selected():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("SKIP  apscheduler not installed")
        return

    db_module.database.update_preferences("default", preferred_days=[])
    scheduler._scheduler = BackgroundScheduler()
    try:
        assert scheduler.sync_slot_job("default")["scheduled"] is False
        assert scheduler._scheduler.get_job(scheduler.SLOT_JOB_ID) is None
    finally:
        scheduler._scheduler = None
        db_module.database.update_preferences(
            "default", preferred_days=["Mon", "Wed", "Fri"]
        )


def test_tick_history_is_recorded():
    db_module.database.record_scheduler_tick(
        action="draft", reason="test", target_time="2026-07-29T09:00:00", late_minutes=149
    )
    ticks = db_module.database.list_scheduler_ticks(limit=5)
    assert ticks and ticks[0]["action"] == "draft"
    assert ticks[0]["late_minutes"] == 149


def test_catch_up_column_exists_on_upgraded_databases():
    """An older database file must gain the new column on open."""
    path = os.path.join(_tmp, "legacy.db")
    import sqlite3

    conn = sqlite3.connect(path)
    conn.executescript(
        """CREATE TABLE user_preferences (
               user_id TEXT PRIMARY KEY DEFAULT 'default',
               active_categories TEXT DEFAULT '[]',
               tone_overrides TEXT DEFAULT '{}',
               preferred_days TEXT DEFAULT '[]',
               style_profile TEXT DEFAULT '{}',
               created_at TEXT NOT NULL,
               updated_at TEXT NOT NULL
           );"""
    )
    conn.commit()
    conn.close()

    upgraded = db_module.Database(path)
    prefs = upgraded.get_preferences("default")
    assert "catch_up_minutes" in prefs


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
