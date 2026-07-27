"""
Background Scheduler for autonomous post generation.

Two modes:
1. APScheduler (local dev) — runs inside the FastAPI process, no Redis needed
2. Celery + Redis (production) — separate worker process, reliable and scalable

The scheduler checks every 30 minutes:
  - Which users have auto_post_enabled = true?
  - Is today one of their preferred_days?
  - Is the current time near their preferred_time?
  - Have they already posted today?
  - If all conditions met → generate and publish a post
"""

import asyncio
import logging
from datetime import datetime, timedelta

from db.database import database

logger = logging.getLogger("scheduler")


# How long after the target time a post may still go out. A laptop that was
# asleep, a server restart, or a missed tick should not silently cost a day's
# post — but nothing should fire at midnight either.
CATCH_UP_MINUTES = 240

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _week_start(now: datetime) -> datetime:
    """Monday 00:00 of the current week."""
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_target(preferred_time: str, now: datetime):
    """Turn the stored preferred time into today's datetime, or None."""
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            return datetime.strptime((preferred_time or "").strip(), fmt).replace(
                year=now.year, month=now.month, day=now.day
            )
        except ValueError:
            continue
    return None


def evaluate(prefs: dict, now: datetime = None) -> dict:
    """Decide whether to post right now, and explain why or why not.

    The scheduler tick and the /api/scheduler/status endpoint both call this,
    so the diagnostic can never drift from what actually happens.
    """
    now = now or datetime.now()
    user_id = prefs.get("user_id", "default")
    today = DAY_NAMES[now.weekday()]
    preferred_days = prefs.get("preferred_days") or []
    cap = prefs.get("posting_frequency") or 0
    preferred_time = prefs.get("preferred_time", "9:00 AM")

    published_this_week = database.count_published_since(
        user_id, _week_start(now).isoformat()
    )
    target = _parse_target(preferred_time, now)

    posted_today = False
    recent = database.list_posts(user_id=user_id, status="published", limit=1)
    if recent:
        posted_today = (recent[0].get("created_at") or "").startswith(
            now.strftime("%Y-%m-%d")
        )

    ctx = {
        "now": now.isoformat(timespec="seconds"),
        "today": today,
        "preferred_days": preferred_days,
        "preferred_time": preferred_time,
        "target_time": target.isoformat(timespec="seconds") if target else None,
        "catch_up_until": (
            (target + timedelta(minutes=CATCH_UP_MINUTES)).isoformat(timespec="seconds")
            if target
            else None
        ),
        "weekly_cap": cap,
        "published_this_week": published_this_week,
        "posted_today": posted_today,
        "active_categories": prefs.get("active_categories") or [],
        "auto_post_enabled": bool(prefs.get("auto_post_enabled")),
    }

    def no(reason):
        return {"should_post": False, "reason": reason, **ctx}

    if not ctx["auto_post_enabled"]:
        return no("Autonomous mode is off")
    if not ctx["active_categories"]:
        return no("No active categories selected in Settings")
    if not preferred_days:
        return no("No days selected in Settings")
    if today not in preferred_days:
        return no(f"{today} is not a selected day ({', '.join(preferred_days)})")
    if target is None:
        return no(f"Could not read the preferred time {preferred_time!r}")
    if cap and published_this_week >= cap:
        return no(f"Weekly cap reached ({published_this_week}/{cap}) — resets Monday")
    if posted_today:
        return no("Already published today")
    if now < target:
        mins = int((target - now).total_seconds() // 60)
        return no(f"Too early — {mins} min until {preferred_time}")
    if now > target + timedelta(minutes=CATCH_UP_MINUTES):
        return no(
            f"Missed today's window — {preferred_time} plus "
            f"{CATCH_UP_MINUTES // 60}h catch-up has passed"
        )

    return {"should_post": True, "reason": "All conditions met", **ctx}


def _should_post_now(prefs: dict) -> bool:
    """Boolean wrapper kept for callers that only need the decision."""
    return evaluate(prefs)["should_post"]



async def _generate_and_publish(user_id: str, prefs: dict):
    """Generate a post and publish it for a user."""
    from agents.graph import generate_post
    from services.linkedin_api import linkedin_service
    import random

    # Pick a random active category
    categories = prefs.get("active_categories", [])
    if not categories:
        logger.warning(f"User {user_id} has no active categories")
        return

    category = random.choice(categories)

    # Get tone for this category
    tone_overrides = prefs.get("tone_overrides", {})
    tone = tone_overrides.get(category, prefs.get("default_tone", "Conversational"))
    fmt = prefs.get("default_format", "story")

    logger.info(f"Auto-generating post for {user_id}: {category} / {tone} / {fmt}")

    try:
        # Run the LangGraph pipeline
        result = await generate_post(
            user_id=user_id,
            category=category,
            topic="",  # Let AI pick
            format=fmt,
            tone=tone,
        )

        if result.get("status") == "failed":
            logger.error(f"Generation failed for {user_id}: {result.get('error')}")
            return

        # Save the post
        import uuid
        post_id = f"auto_{uuid.uuid4().hex[:12]}"
        database.create_post(
            post_id=post_id,
            title=result.get("final_title", "Auto-generated"),
            content=result.get("final_post", ""),
            category=category,
            user_id=user_id,
            format=fmt,
            tone=tone,
            status="draft",
            style_score=result.get("style_score"),
        )

        # If autonomous mode, publish directly
        if prefs.get("auto_post_enabled"):
            try:
                pub_result = await linkedin_service.create_text_post(
                    result.get("final_post", ""), user_id=user_id
                )
                if pub_result.get("status") == "published":
                    database.update_post(post_id, status="published")
                    logger.info(f"Auto-published post {post_id} for {user_id}")
                else:
                    database.update_post(post_id, status="scheduled")
                    logger.warning(f"LinkedIn publish failed for {user_id}, saved as scheduled")
            except Exception as e:
                database.update_post(post_id, status="scheduled")
                logger.warning(f"LinkedIn publish error for {user_id}: {e}")

    except Exception as e:
        logger.error(f"Auto-generation error for {user_id}: {e}")


_last_tick: dict = {"at": None, "reason": "Not run yet"}


def last_tick() -> dict:
    """What the most recent tick decided. Surfaced by /api/scheduler/status."""
    return dict(_last_tick)


async def run_scheduler_tick():
    """One tick of the scheduler — check the user and generate if needed."""
    # For now, just the default user. In production, iterate all users.
    try:
        prefs = database.get_preferences("default")
        decision = evaluate(prefs)
        _last_tick["at"] = datetime.now().isoformat(timespec="seconds")
        _last_tick["reason"] = decision["reason"]

        if decision["should_post"]:
            logger.info("Scheduler tick — conditions met, generating post")
            await _generate_and_publish("default", prefs)
        else:
            logger.info(f"Scheduler tick — no post: {decision['reason']}")
    except Exception as e:
        _last_tick["at"] = datetime.now().isoformat(timespec="seconds")
        _last_tick["reason"] = f"Error: {e}"
        logger.error(f"Scheduler error: {e}", exc_info=True)


# ─── APScheduler (local dev mode) ────────────────────────────────

_scheduler = None


# Ticks are cheap — they only read preferences — so run often. The "already
# posted today" guard is what prevents duplicates, not the tick spacing.
TICK_MINUTES = 10


def scheduler_info() -> dict:
    """Whether the background job is alive and when it next runs."""
    if not _scheduler:
        return {"running": False, "next_run": None, "tick_minutes": TICK_MINUTES}
    job = _scheduler.get_job("auto_post_check")
    return {
        "running": bool(_scheduler.running),
        "next_run": job.next_run_time.isoformat(timespec="seconds") if job and job.next_run_time else None,
        "tick_minutes": TICK_MINUTES,
    }


def start_local_scheduler():
    """Start APScheduler for local development. Runs inside FastAPI process."""
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            run_scheduler_tick,
            "interval",
            minutes=TICK_MINUTES,
            id="auto_post_check",
            replace_existing=True,
            # Without a grace time APScheduler drops any run it is more than one
            # second late for. A reloading dev server or a sleeping laptop is
            # routinely later than that, which silently skips every tick.
            misfire_grace_time=TICK_MINUTES * 60,
            # If several runs were missed, catch up with one, not a burst.
            coalesce=True,
            max_instances=1,
            # Evaluate shortly after boot so enabling autonomous mode doesn't
            # wait a full interval to take effect.
            next_run_time=datetime.now() + timedelta(seconds=20),
        )
        _scheduler.start()
        logger.info(
            f"Local scheduler started (APScheduler, {TICK_MINUTES}-min interval, "
            f"{TICK_MINUTES}-min misfire grace)"
        )
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
    except Exception as e:
        logger.warning(f"Could not start scheduler: {e}")


def stop_local_scheduler():
    """Stop the local scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Local scheduler stopped")


# ─── Celery (production mode) ────────────────────────────────────
# To use Celery instead:
#   1. Install Redis: brew install redis && redis-server
#   2. Set REDIS_URL in .env
#   3. Run worker: celery -A services.scheduler worker --beat --loglevel=info
#
# The Celery setup would look like:
#
# from celery import Celery
# from celery.schedules import crontab
#
# celery_app = Celery("linkedin_gen", broker=settings.REDIS_URL)
# celery_app.conf.beat_schedule = {
#     "check-auto-post": {
#         "task": "services.scheduler.celery_tick",
#         "schedule": crontab(minute="*/30"),
#     },
# }
#
# @celery_app.task
# def celery_tick():
#     asyncio.run(run_scheduler_tick())
