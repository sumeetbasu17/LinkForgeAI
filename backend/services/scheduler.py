"""
Background Scheduler for autonomous post generation.

Two modes:
1. APScheduler (local dev) — runs inside the FastAPI process, no Redis needed
2. Celery + Redis (production) — separate worker process, reliable and scalable

Every tick (see TICK_MINUTES) the scheduler asks:
  - Is auto_post_enabled = true?
  - Is today one of their preferred_days?
  - Are we inside the publishing window — preferred_time plus catch_up_minutes?
  - Have they already posted today, or is the weekly cap used up?

Inside the window it generates and publishes. Past the window it generates and
saves a DRAFT: the scheduler runs inside the API process, so a machine asleep at
09:00 means the first tick of the day can be hours late, and publishing then
would put a post out at a time the user never picked.

Every tick is written to the scheduler_ticks table. A gap in that history is
what proves the backend was down, which is the usual cause of a missed slot.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from db.database import database

logger = logging.getLogger("scheduler")


# How long after the target time a post may still be PUBLISHED. This scheduler
# lives inside the FastAPI process, so it only ticks while the backend is up: a
# sleeping laptop at 9:00 AM means the first tick of the day can land hours
# late. Publishing then puts a post out at a time the user never chose, so past
# this window the post is generated and saved as a draft instead.
# Overridable per user via the catch_up_minutes preference.
DEFAULT_CATCH_UP_MINUTES = 15

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Posts the scheduler creates are prefixed so they can be told apart from
# hand-generated ones — used by the once-a-day draft guard.
AUTO_PREFIX = "auto_"


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
    """Decide what to do right now, and explain why.

    Returns an "action":
      * "publish" — inside the slot: generate and post to LinkedIn
      * "draft"   — the slot was missed: generate and save a draft to review
      * "none"    — do nothing (with a reason)

    The scheduler tick and the /api/scheduler/status endpoint both call this,
    so the diagnostic can never drift from what actually happens.
    """
    now = now or datetime.now()
    user_id = prefs.get("user_id", "default")
    today = DAY_NAMES[now.weekday()]
    preferred_days = prefs.get("preferred_days") or []
    cap = prefs.get("posting_frequency") or 0
    preferred_time = prefs.get("preferred_time", "9:00 AM")
    window = prefs.get("catch_up_minutes")
    window = DEFAULT_CATCH_UP_MINUTES if window is None else int(window)

    published_this_week = database.count_published_since(
        user_id, _week_start(now).isoformat()
    )
    target = _parse_target(preferred_time, now)

    # "Today" is taken from `now` rather than the wall clock so that the status
    # endpoint and the tests can evaluate any moment consistently.
    day = now.strftime("%Y-%m-%d")
    posted_today = database.count_posts_today(user_id, status="published", day=day) > 0
    drafted_today = (
        database.count_posts_today(
            user_id, status="draft", id_prefix=AUTO_PREFIX, day=day
        )
        > 0
    )
    late_minutes = int((now - target).total_seconds() // 60) if target else 0

    ctx = {
        "now": now.isoformat(timespec="seconds"),
        "today": today,
        "preferred_days": preferred_days,
        "preferred_time": preferred_time,
        "target_time": target.isoformat(timespec="seconds") if target else None,
        "catch_up_minutes": window,
        "publish_until": (
            (target + timedelta(minutes=window)).isoformat(timespec="seconds")
            if target
            else None
        ),
        "late_minutes": max(0, late_minutes),
        "weekly_cap": cap,
        "published_this_week": published_this_week,
        "posted_today": posted_today,
        "drafted_today": drafted_today,
        "active_categories": prefs.get("active_categories") or [],
        "auto_post_enabled": bool(prefs.get("auto_post_enabled")),
    }

    def decide(action, reason):
        return {"action": action, "should_post": action != "none", "reason": reason, **ctx}

    def no(reason):
        return decide("none", reason)

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

    if late_minutes <= window:
        return decide("publish", f"In the {preferred_time} slot (+{late_minutes} min)")

    # The slot has passed. Never publish hours late behind the user's back —
    # write one draft for the day and leave the decision to them.
    if drafted_today:
        return no(
            f"Missed the {preferred_time} slot by {late_minutes} min — "
            "a draft for today is already saved"
        )
    return decide(
        "draft",
        f"Missed the {preferred_time} slot by {late_minutes} min "
        f"(window is {window} min) — saving a draft instead of publishing late",
    )


def _should_post_now(prefs: dict) -> bool:
    """Boolean wrapper kept for callers that only need the decision."""
    return evaluate(prefs)["should_post"]



async def _generate_and_publish(user_id: str, prefs: dict, publish: bool = True):
    """Generate a post, then publish it or save it as a draft.

    publish=False is the missed-slot path: the post is still written (so the
    day's material isn't lost) but it waits in Drafts for the user.
    """
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
        post_id = f"{AUTO_PREFIX}{uuid.uuid4().hex[:12]}"
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

        # The pipeline's visual step already judged whether this post earns an
        # image and wrote the card content. Render it here, with the presets and
        # handles configured in the Images tab. Most posts get nothing — that is
        # the intended behaviour, a weak card is worse than none.
        image_path = None
        if result.get("wants_image") and result.get("image_payload"):
            try:
                from services import image_pipeline

                record = await image_pipeline.render_for_post(
                    archetype=result.get("image_archetype", "social-card"),
                    payload=result["image_payload"],
                    user_id=user_id,
                    post_id=post_id,
                )
                image_path = record["path"]
                logger.info(
                    f"Rendered {record['archetype']} for {post_id}: {record['url']}"
                )
            except Exception as e:
                logger.warning(f"Image render skipped for {post_id}: {str(e)[:200]}")

        if not publish:
            logger.info(
                f"Saved draft {post_id} for {user_id} — outside the publishing window"
            )
            return

        # Inside the slot: publish for real.
        if prefs.get("auto_post_enabled"):
            try:
                text = result.get("final_post", "")
                pub_result = None
                if image_path:
                    # An image post that fails to upload must not cost the post,
                    # so fall through to text-only.
                    pub_result = await linkedin_service.create_image_post(
                        text,
                        str(image_path),
                        user_id=user_id,
                        alt_text=result.get("final_title", ""),
                    )
                    if pub_result.get("status") != "published":
                        logger.warning(
                            f"Image post failed ({pub_result.get('message')}) — "
                            "retrying as text only"
                        )
                        pub_result = None
                if pub_result is None:
                    pub_result = await linkedin_service.create_text_post(
                        text, user_id=user_id
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


_last_tick: dict = {"at": None, "reason": "Not run yet", "action": "none"}


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
        _last_tick["action"] = decision["action"]

        # Every tick is logged, so a gap in the history is the proof that the
        # backend was not running — which is the usual reason a slot is missed.
        database.record_scheduler_tick(
            user_id="default",
            action=decision["action"],
            reason=decision["reason"],
            target_time=decision.get("target_time") or "",
            late_minutes=decision.get("late_minutes") or 0,
        )

        if decision["action"] == "publish":
            logger.info("Scheduler tick — in the slot, generating and publishing")
            await _generate_and_publish("default", prefs, publish=True)
        elif decision["action"] == "draft":
            logger.warning(f"Scheduler tick — {decision['reason']}")
            await _generate_and_publish("default", prefs, publish=False)
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


SLOT_JOB_ID = "auto_post_slot"
TICK_JOB_ID = "auto_post_check"

_CRON_DAYS = {
    "Mon": "mon", "Tue": "tue", "Wed": "wed", "Thu": "thu",
    "Fri": "fri", "Sat": "sat", "Sun": "sun",
}


def _next_run(job_id: str):
    job = _scheduler.get_job(job_id) if _scheduler else None
    return (
        job.next_run_time.isoformat(timespec="seconds")
        if job and job.next_run_time
        else None
    )


def scheduler_info() -> dict:
    """Whether the background jobs are alive and when they next run."""
    if not _scheduler:
        return {
            "running": False,
            "next_run": None,
            "next_slot": None,
            "tick_minutes": TICK_MINUTES,
        }
    return {
        "running": bool(_scheduler.running),
        # The safety-net tick.
        "next_run": _next_run(TICK_JOB_ID),
        # The exact-time job — this is the one that fires at 9:00:00 sharp.
        "next_slot": _next_run(SLOT_JOB_ID),
        "tick_minutes": TICK_MINUTES,
    }


def sync_slot_job(user_id: str = "default") -> dict:
    """(Re)register a cron job that fires exactly at the user's chosen time.

    The 10-minute tick alone means a 9:00 AM post actually goes out somewhere
    in 9:00–9:10, which is not what the user asked for. This adds a cron
    trigger on the preferred days at the preferred hour and minute, so the
    normal case fires on the second. The interval tick stays as the safety net
    that catches a missed slot and saves a draft.

    Called at startup and again whenever preferences change.
    """
    if not _scheduler:
        return {"scheduled": False, "reason": "Scheduler not running"}

    prefs = database.get_preferences(user_id)
    days = [_CRON_DAYS[d] for d in (prefs.get("preferred_days") or []) if d in _CRON_DAYS]
    target = _parse_target(prefs.get("preferred_time", "9:00 AM"), datetime.now())

    existing = _scheduler.get_job(SLOT_JOB_ID)
    if not days or target is None:
        if existing:
            _scheduler.remove_job(SLOT_JOB_ID)
        return {"scheduled": False, "reason": "No days or unreadable time"}

    from apscheduler.triggers.cron import CronTrigger

    _scheduler.add_job(
        run_scheduler_tick,
        CronTrigger(
            day_of_week=",".join(days), hour=target.hour, minute=target.minute
        ),
        id=SLOT_JOB_ID,
        replace_existing=True,
        # A few minutes of grace covers a busy event loop, but not a closed app.
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        f"Slot job set for {prefs.get('preferred_time')} on "
        f"{','.join(days)} (next: {_next_run(SLOT_JOB_ID)})"
    )
    return {"scheduled": True, "next_slot": _next_run(SLOT_JOB_ID)}


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
            id=TICK_JOB_ID,
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
        # Exact-time job for the configured slot; the interval above is only the
        # net that catches a slot missed because the app was closed.
        sync_slot_job("default")
        logger.info(
            f"Local scheduler started (APScheduler, {TICK_MINUTES}-min safety tick "
            f"+ exact cron slot)"
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
