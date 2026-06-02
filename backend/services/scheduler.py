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


def _should_post_now(prefs: dict) -> bool:
    """Check if a user should get a post generated right now."""
    if not prefs.get("auto_post_enabled"):
        return False

    now = datetime.now()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    current_day = day_names[now.weekday()]

    # Is today a preferred day?
    preferred_days = prefs.get("preferred_days", [])
    if current_day not in preferred_days:
        return False

    # Is it within 30 minutes of preferred time?
    preferred_time = prefs.get("preferred_time", "9:00 AM")
    try:
        target = datetime.strptime(preferred_time, "%I:%M %p").replace(
            year=now.year, month=now.month, day=now.day
        )
        diff = abs((now - target).total_seconds())
        if diff > 1800:  # Not within 30 min window
            return False
    except ValueError:
        return False

    # Check if already posted today
    posts = database.list_posts(
        user_id=prefs["user_id"], status="published", limit=1
    )
    if posts:
        last_post_date = posts[0].get("created_at", "")
        if last_post_date.startswith(now.strftime("%Y-%m-%d")):
            return False  # Already posted today

    return True


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


async def run_scheduler_tick():
    """One tick of the scheduler — check all users and generate if needed.

    Called every 30 minutes by the background loop.
    """
    logger.info("Scheduler tick — checking users...")

    # Get all users with auto_post enabled
    # For now, just check the default user. In production, iterate all users.
    try:
        prefs = database.get_preferences("default")
        if _should_post_now(prefs):
            logger.info("Conditions met — generating post...")
            await _generate_and_publish("default", prefs)
        else:
            logger.info("No post needed right now")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")


# ─── APScheduler (local dev mode) ────────────────────────────────

_scheduler = None


def start_local_scheduler():
    """Start APScheduler for local development. Runs inside FastAPI process."""
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            run_scheduler_tick,
            "interval",
            minutes=30,
            id="auto_post_check",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Local scheduler started (APScheduler, 30-min interval)")
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
