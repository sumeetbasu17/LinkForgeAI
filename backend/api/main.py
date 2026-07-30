"""
FastAPI application — all API routes for the LinkedIn Post Generator.

Routes:
  POST /api/generate          — Generate a new post via LangGraph pipeline
  GET  /api/posts             — List all posts
  GET  /api/posts/{id}        — Get a specific post
  PUT  /api/posts/{id}        — Update a post
  DELETE /api/posts/{id}      — Delete a post
  POST /api/style/posts       — Add a style post (own or inspiration)
  GET  /api/style/posts       — List style posts
  POST /api/style/analyze     — Trigger style analysis
  GET  /api/style/profile     — Get current style profile
  GET  /api/preferences       — Get user preferences
  PUT  /api/preferences       — Update user preferences
  GET  /api/config            — Get app config (categories, formats, tones)
"""

import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from api.schemas import (
    GeneratePostRequest,
    GeneratePostResponse,
    PostUpdate,
    PostResponse,
    AddStylePostRequest,
    AddStylePostsBulkRequest,
    SplitPreviewRequest,
    StylePostResponse,
    PreferencesUpdate,
    PreferencesResponse,
    ConfigResponse,
    AnalyzeStyleRequest,
    StyleProfileResponse,
)
from api.auth import get_current_user
from agents.graph import generate_post
from db.database import database
from db.vector_store import vector_store
from services.style_analyzer import style_analyzer
from services.scheduler import start_local_scheduler, stop_local_scheduler
from config.settings import settings

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on startup, stop on shutdown."""
    start_local_scheduler()
    yield
    stop_local_scheduler()


app = FastAPI(
    title="LinkedIn Post Generator API",
    description="AI-powered LinkedIn content engine for senior SDEs",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health Check ─────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0", "auth_enabled": settings.AUTH_ENABLED}


@app.get("/api/test-llm")
async def test_llm():
    """Test OpenRouter connection. Visit http://localhost:8000/api/test-llm in browser."""
    from services.llm import llm_service

    if not settings.OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY is empty in .env", "fix": "Add your key from openrouter.ai/keys"}

    try:
        result = await llm_service.call_light(
            "You are a helpful assistant.",
            "Say 'Connection works!' in exactly those two words.",
        )
        return {
            "status": "success",
            "response": result,
            "model_used": settings.LLM_MODEL_LIGHT,
            "heavy_model": settings.LLM_MODEL,
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "model_attempted": settings.LLM_MODEL_LIGHT,
            "api_key_prefix": settings.OPENROUTER_API_KEY[:8] + "..." if settings.OPENROUTER_API_KEY else "EMPTY",
            "fix": "Check: 1) API key is correct 2) You have credits at openrouter.ai 3) Model ID exists on openrouter.ai",
        }


# ─── Config ───────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Get app configuration: categories, formats, tones, models."""
    return {
        "categories": settings.DEFAULT_CATEGORIES,
        "formats": settings.DEFAULT_POST_FORMATS,
        "tones": settings.DEFAULT_TONES,
        "models": settings.AVAILABLE_MODELS,
        "auth_enabled": settings.AUTH_ENABLED,
    }


# ─── Post Generation ─────────────────────────────────────────────

@app.post("/api/generate", response_model=GeneratePostResponse)
async def generate(req: GeneratePostRequest):
    """Generate a new LinkedIn post using the LangGraph agent pipeline.

    An explicit choice always wins. Settings act as defaults, filling in only
    what the request leaves blank — so the tone shown in the Generate tab is
    the tone the post is actually written in.
    """
    prefs = database.get_preferences(req.user_id)

    tone = req.tone
    if not tone:
        # Nothing chosen — fall back to the category's tone, then the default.
        tone = prefs.get("tone_overrides", {}).get(
            req.category, prefs.get("default_tone", "Conversational")
        )

    fmt = req.format or prefs.get("default_format", "story")

    # Run the agent pipeline
    result = await generate_post(
        user_id=req.user_id,
        category=req.category,
        topic=req.topic,
        format=fmt,
        tone=tone,
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))

    # Save to database
    post_id = f"post_{uuid.uuid4().hex[:12]}"
    post = database.create_post(
        post_id=post_id,
        title=result.get("final_title", result.get("draft_title", "Untitled")),
        content=result.get("final_post", result.get("draft_content", "")),
        category=req.category,
        user_id=req.user_id,
        format=fmt,
        tone=tone,
        status="draft",
        research_data={"summary": result.get("research_summary", "")},
        style_score=result.get("style_score"),
    )

    return GeneratePostResponse(
        post_id=post_id,
        title=post["title"],
        content=post["content"],
        category=post["category"],
        format=post["format"],
        tone=post["tone"],
        style_score=result.get("style_score", 0),
        status="draft",
        research_summary=result.get("research_summary", ""),
        selected_topic=result.get("selected_topic", ""),
        revision_count=result.get("revision_count", 0),
        wants_image=result.get("wants_image", False),
        image_archetype=result.get("image_archetype", ""),
        image_reason=result.get("image_reason", ""),
        image_payload=result.get("image_payload", {}) or {},
    )


# ─── Posts CRUD ───────────────────────────────────────────────────

@app.get("/api/posts")
async def list_posts(
    user_id: str = "default",
    status: str = None,
    category: str = None,
    limit: int = 50,
):
    """List all posts with optional filters."""
    posts = database.list_posts(user_id=user_id, status=status, category=category, limit=limit)
    return {"posts": posts, "total": len(posts)}


@app.get("/api/posts/{post_id}")
async def get_post(post_id: str):
    """Get a specific post."""
    post = database.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.put("/api/posts/{post_id}")
async def update_post(post_id: str, update: PostUpdate):
    """Update a post (content, status, schedule, etc.)."""
    existing = database.get_post(post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    updated = database.update_post(post_id, **update_data)
    return updated


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: str):
    """Delete a post."""
    deleted = database.delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"deleted": True, "id": post_id}


# ─── Style Posts ──────────────────────────────────────────────────

from services.auto_categorizer import auto_categorizer
from services import article_parser

@app.post("/api/style/posts")
async def add_style_post(req: AddStylePostRequest, user_id: str = Depends(get_current_user)):
    """Add a post for style learning. Auto-detects category if not provided."""
    post_id = f"style_{uuid.uuid4().hex[:12]}"
    uid = req.user_id if req.user_id != "default" else user_id

    # Auto-categorize if no category selected
    category = req.category
    auto_detected = False
    if not category:
        category = await auto_categorizer.categorize_single(req.content)
        auto_detected = bool(category)

    database.add_style_post(
        post_id=post_id, content=req.content, post_type=req.post_type,
        user_id=uid, category=category, source_url=req.source_url,
    )
    vector_store.add_post(
        user_id=uid, content=req.content, category=category,
        post_type=req.post_type, post_id=post_id,
    )
    cat_label = category or "uncategorized"
    return {
        "id": post_id,
        "content": req.content[:100] + "..." if len(req.content) > 100 else req.content,
        "post_type": req.post_type, "category": category,
        "auto_detected": auto_detected,
        "message": f"Added to {cat_label}" + (" (auto-detected)" if auto_detected else ""),
    }


@app.post("/api/style/preview")
async def preview_style_split(req: SplitPreviewRequest):
    """Dry-run the article splitter on pasted text.

    The paste box used to store whatever was in it as one row, so pasting ten
    articles created one ten-article post. The UI now previews the split first
    and asks before adding, and this endpoint does the parsing half.

    Nothing is written to the database here.
    """
    parsed = article_parser.split_into_articles(req.content or "")
    articles = parsed["articles"]
    return {
        "method": parsed["method"],
        "count": len(articles),
        "skipped": parsed["skipped"],
        "numbering_gaps": parsed["gaps"],
        "articles": [
            {
                "content": a["content"],
                "number": a.get("number"),
                "url": a.get("url", ""),
                "preview": a["content"][:120],
                "words": len(a["content"].split()),
            }
            for a in articles
        ],
    }


@app.post("/api/style/posts/bulk")
async def add_style_posts_bulk(
    req: AddStylePostsBulkRequest, user_id: str = Depends(get_current_user)
):
    """Add several style posts in one call, auto-categorizing each one."""
    uid = req.user_id if req.user_id != "default" else user_id
    contents = [c.strip() for c in req.contents if c and c.strip()]
    if not contents:
        raise HTTPException(status_code=400, detail="No content to add")

    categories = [req.category] * len(contents)
    auto_detected = 0
    if not req.category:
        detected = await auto_categorizer.categorize_batch(contents)
        categories = [c or "" for c in detected]
        auto_detected = sum(1 for c in categories if c)

    added = []
    for content, category in zip(contents, categories):
        post_id = f"style_{uuid.uuid4().hex[:12]}"
        database.add_style_post(
            post_id=post_id, content=content, post_type=req.post_type,
            user_id=uid, category=category, source_url=req.source_url,
        )
        vector_store.add_post(
            user_id=uid, content=content, category=category,
            post_type=req.post_type, post_id=post_id,
        )
        added.append({"id": post_id, "category": category})

    message = f"{len(added)} posts added"
    if not req.category:
        message += f", {auto_detected} auto-categorized"
        if auto_detected < len(added):
            message += f" ({len(added) - auto_detected} need a category)"
    return {
        "added": len(added),
        "posts": added,
        "post_type": req.post_type,
        "auto_categorized": auto_detected,
        "message": message,
    }


@app.get("/api/style/posts")
async def list_style_posts(
    user_id: str = "default", post_type: str = None, category: str = None,
):
    """List style posts with optional category filter."""
    posts = database.get_style_posts(user_id=user_id, post_type=post_type, category=category)
    return {"posts": posts, "total": len(posts)}


@app.get("/api/style/counts")
async def get_style_counts(user_id: str = "default"):
    """Get style post counts grouped by category and type."""
    return database.get_style_post_counts(user_id)


@app.delete("/api/style/posts/{post_id}")
async def delete_style_post(post_id: str):
    """Delete a single style post."""
    deleted = database.delete_style_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Style post not found")
    return {"deleted": True, "id": post_id}


@app.delete("/api/style/posts")
async def delete_style_posts_bulk(
    user_id: str = "default",
    category: str = None,
    post_type: str = None,
    delete_all: bool = False,
):
    """Delete style posts by category, by type, or all at once.

    Examples:
      DELETE /api/style/posts?category=system-design       → delete all in that category
      DELETE /api/style/posts?post_type=inspiration         → delete all inspiration posts
      DELETE /api/style/posts?category=ai-engineering&post_type=own → delete own posts in AI category
      DELETE /api/style/posts?delete_all=true               → delete everything
    """
    if delete_all:
        count = database.delete_all_style_posts(user_id=user_id, post_type=post_type)
        return {"deleted_count": count, "scope": "all"}
    elif category:
        count = database.delete_style_posts_by_category(
            user_id=user_id, category=category, post_type=post_type,
        )
        return {"deleted_count": count, "category": category}
    else:
        raise HTTPException(status_code=400, detail="Specify category, post_type, or delete_all=true")


@app.post("/api/style/upload")
async def upload_style_file(
    file: UploadFile = File(...),
    post_type: str = Form("own"),
    category: str = Form(""),
    user_id: str = Form("default"),
):
    """Upload a file with multiple articles. Auto-categorizes if no category selected.

    Supported formats:
      - .pdf: Extracted as one continuous document, then split on 'Article N :'
              headers (typo tolerant), separators, post URLs, or blank lines
      - .txt: Same splitting rules as PDF
      - .csv: Columns 'content', optional 'category', 'url'
      - .json: Array of {"content": "...", "category": "...", "url": "..."}

    If category is empty (Auto-detect), EVERY article is classified by AI.
    If category is set, ALL articles get that category.
    """
    content_bytes = await file.read()
    filename = file.filename or ""
    use_auto = not category

    try:
        parsed = article_parser.parse_upload(content_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:300])
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Could not read file: {str(e)[:300]}"
        )

    parsed_articles = parsed["articles"]
    if not parsed_articles:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No articles found (each must be at least "
                f"{article_parser.MIN_ARTICLE_CHARS} characters)."
            ),
        )

    # Auto-categorize every article that doesn't already carry a category
    auto_detected = 0
    if use_auto:
        pending = [i for i, a in enumerate(parsed_articles) if not a["category"]]
        if pending:
            cats = await auto_categorizer.categorize_batch(
                [parsed_articles[i]["content"] for i in pending]
            )
            for i, cat in zip(pending, cats):
                parsed_articles[i]["category"] = cat
                if cat:
                    auto_detected += 1

    added = 0
    for art in parsed_articles:
        pid = f"style_{uuid.uuid4().hex[:12]}"
        art_cat = art["category"] or category
        database.add_style_post(
            pid, art["content"], post_type, user_id, art_cat, art.get("url", "")
        )
        vector_store.add_post(user_id, art["content"], art_cat, post_type, pid)
        added += 1

    result = {
        "added": added,
        "post_type": post_type,
        "split_method": parsed["method"],
        "skipped": parsed["skipped"],
        "numbering_gaps": parsed["gaps"],
    }

    message = f"{added} articles imported"
    if use_auto:
        result["auto_categorized"] = auto_detected
        message += f", {auto_detected} auto-categorized"
        if auto_detected < added:
            message += f" ({added - auto_detected} need a category)"
    else:
        result["category"] = category
        message += f" to {category}"
    if parsed["skipped"]:
        message += f" · {parsed['skipped']} fragment(s) too short, skipped"
    if parsed["gaps"]:
        gaps = ", ".join(str(g) for g in parsed["gaps"][:10])
        message += f" · numbering gap at article {gaps} (missing in the file)"
    result["message"] = message
    return result


@app.post("/api/style/recategorize")
async def recategorize_style_posts(
    user_id: str = "default",
    post_type: str = None,
    only_uncategorized: bool = True,
):
    """Backfill categories on posts already in the library.

    Lets the user repair an earlier import without re-uploading anything.
    Set only_uncategorized=false to re-classify everything from scratch.
    """
    posts = database.get_style_posts(user_id=user_id, post_type=post_type)
    targets = [p for p in posts if not p.get("category")] if only_uncategorized else posts

    if not targets:
        return {"updated": 0, "message": "Nothing to categorize — all posts already have one."}

    cats = await auto_categorizer.categorize_batch([p["content"] for p in targets])

    updated = 0
    for post, cat in zip(targets, cats):
        if not cat or cat == post.get("category"):
            continue
        database.update_style_post_category(post["id"], cat)
        vector_store.update_post_category(post["id"], cat)
        updated += 1

    return {
        "updated": updated,
        "examined": len(targets),
        "message": f"{updated} of {len(targets)} posts categorized",
    }


@app.post("/api/style/analyze")
async def analyze_style(req: AnalyzeStyleRequest):
    """Trigger style analysis on all of the user's uploaded posts."""
    style_posts = database.get_style_posts(user_id=req.user_id, post_type="own")
    contents = [p["content"] for p in style_posts]

    if not contents:
        raise HTTPException(status_code=400, detail="No posts uploaded yet.")

    profile = await style_analyzer.analyze_posts_full(contents)
    database.update_preferences(req.user_id, style_profile=profile.to_dict())

    return {
        "avg_word_count": profile.avg_word_count,
        "avg_paragraph_count": profile.avg_paragraph_count,
        "uses_code_blocks": profile.uses_code_blocks,
        "uses_arrow_bullets": profile.uses_arrow_bullets,
        "hook_style": profile.hook_style,
        "cta_style": profile.cta_style,
        "formatting_style": profile.formatting_style,
        "voice_description": profile.voice_description,
        "tone_keywords": profile.tone_keywords,
        "emoji_style": profile.emoji_style,
        "post_count": len(contents),
    }


@app.get("/api/style/profile")
async def get_style_profile(user_id: str = "default"):
    """Get the current style profile."""
    prefs = database.get_preferences(user_id)
    profile = prefs.get("style_profile", {})
    style_posts = database.get_style_posts(user_id=user_id, post_type="own")
    profile["post_count"] = len(style_posts)
    return profile


# ─── Model Selection ─────────────────────────────────────────────

@app.get("/api/models")
async def list_models():
    """List available LLM models."""
    return {"models": settings.AVAILABLE_MODELS}

@app.put("/api/models/select")
async def select_model(model_id: str, user_id: str = "default"):
    """Set the preferred LLM model for a user."""
    valid_ids = [m["id"] for m in settings.AVAILABLE_MODELS]
    if model_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Invalid model. Choose from: {valid_ids}")

    database.update_preferences(user_id, preferred_model=model_id)
    return {"selected": model_id}


# ─── Custom Rules ─────────────────────────────────────────────────

@app.get("/api/rules")
async def get_rules(user_id: str = "default"):
    """Get custom generation rules."""
    prefs = database.get_preferences(user_id)
    return {"rules": prefs.get("custom_rules", "")}

@app.put("/api/rules")
async def update_rules(rules: str, user_id: str = "default"):
    """Save custom generation rules.

    Example rules:
      - Never write about building in public
      - Don't mention personal interview experiences
      - Avoid words: synergy, leverage, game-changer
      - Always include a code example in technical posts
    """
    database.update_preferences(user_id, custom_rules=rules)
    return {"rules": rules, "message": "Rules saved. They'll apply to all future posts."}


# ─── Preferences ──────────────────────────────────────────────────

@app.get("/api/preferences")
async def get_preferences(user_id: str = "default"):
    """Get user preferences."""
    prefs = database.get_preferences(user_id)
    prefs["auto_post_enabled"] = bool(prefs.get("auto_post_enabled", 0))
    return prefs


@app.put("/api/preferences")
async def update_preferences(update: PreferencesUpdate, user_id: str = "default"):
    """Update user preferences."""
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if "auto_post_enabled" in update_data:
        update_data["auto_post_enabled"] = int(update_data["auto_post_enabled"])
        update_data["auto_post_enabled"] = int(update_data["auto_post_enabled"])

    database.update_preferences(user_id, **update_data)

    # Changing the day or the time must move the exact-time job, not wait for a
    # restart to pick it up.
    if {"preferred_days", "preferred_time"} & set(update_data):
        from services import scheduler as sched

        sched.sync_slot_job(user_id)

    return await get_preferences(user_id)


# ─── Carousel Generator ──────────────────────────────────────────

from services.carousel import carousel_generator

@app.post("/api/carousel")
async def generate_carousel(post_id: str = "", content: str = "", num_slides: int = 8):
    """Generate carousel slides from a post."""
    if post_id:
        post = database.get_post(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]
    if not content:
        raise HTTPException(status_code=400, detail="Provide post_id or content")

    slides = await carousel_generator.generate_slides(content, num_slides)
    return {"slides": slides, "total": len(slides)}


# ─── Hook A/B Tester ─────────────────────────────────────────────

from services.hook_tester import hook_tester

@app.post("/api/hooks")
async def generate_hooks(post_id: str = "", content: str = "", count: int = 3):
    """Generate multiple hook variations for a post."""
    if post_id:
        post = database.get_post(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]
    if not content:
        raise HTTPException(status_code=400, detail="Provide post_id or content")

    hooks = await hook_tester.generate_hooks(content, count)
    return {"hooks": hooks}


@app.post("/api/hooks/apply")
async def apply_hook(post_id: str, hook: str):
    """Apply a chosen hook to a post."""
    post = database.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    new_content = await hook_tester.apply_best_hook(post["content"], hook)
    database.update_post(post_id, content=new_content)
    return {"content": new_content, "message": "Hook applied"}


# ─── Comment Engagement Agent ────────────────────────────────────

from services.comment_agent import comment_agent
from pydantic import BaseModel

class CommentReplyRequest(BaseModel):
    post_content: str
    comment_text: str
    commenter_name: str = ""
    tone: str = "Conversational"

class ProactiveCommentRequest(BaseModel):
    target_post: str
    expertise: str = "Senior SDE with 12+ years in backend engineering"
    tone: str = "Conversational"

class BatchReplyRequest(BaseModel):
    post_content: str
    comments: list[dict]
    tone: str = "Conversational"

@app.post("/api/comments/reply")
async def draft_comment_reply(req: CommentReplyRequest):
    """Draft a reply to a comment on your post."""
    result = await comment_agent.draft_reply(
        req.post_content, req.comment_text, req.commenter_name, req.tone,
    )
    return result

@app.post("/api/comments/proactive")
async def draft_proactive_comment(req: ProactiveCommentRequest):
    """Draft a thoughtful comment on someone else's post."""
    result = await comment_agent.draft_proactive_comment(
        req.target_post, req.expertise, req.tone,
    )
    return result

@app.post("/api/comments/batch")
async def batch_draft_replies(req: BatchReplyRequest):
    """Draft replies for multiple comments at once."""
    results = await comment_agent.batch_draft_replies(
        req.post_content, req.comments, req.tone,
    )
    return {"replies": results}


# ─── Content Repurposer ──────────────────────────────────────────

from services.repurposer import content_repurposer

class RepurposeRequest(BaseModel):
    content: str = ""
    post_id: str = ""
    formats: list[str] = ["twitter_thread", "newsletter", "blog_intro", "video_script"]

@app.post("/api/repurpose")
async def repurpose_content(req: RepurposeRequest):
    """Repurpose a LinkedIn post into other content formats."""
    content = req.content
    if req.post_id:
        post = database.get_post(req.post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]
    if not content:
        raise HTTPException(status_code=400, detail="Provide post_id or content")

    results = await content_repurposer.repurpose(content, formats=req.formats)
    return {"repurposed": results, "formats_generated": list(results.keys())}


# ─── Hashtag Optimizer ────────────────────────────────────────────

from services.hashtag_optimizer import hashtag_optimizer

@app.post("/api/hashtags")
async def optimize_hashtags(content: str, category: str = "", count: int = 4):
    """Get optimized hashtags for a post."""
    result = await hashtag_optimizer.optimize(content, category, count)
    return result


# ─── Engagement Predictor & Analytics ─────────────────────────────

from services.engagement_predictor import engagement_predictor

@app.post("/api/predict")
async def predict_engagement(content: str, category: str = "", format: str = ""):
    """Score a post's engagement potential before publishing."""
    result = await engagement_predictor.predict_engagement(content, category, format)
    return result

@app.get("/api/analytics")
async def get_analytics(user_id: str = "default"):
    """Get content performance analytics."""
    return engagement_predictor.get_content_analytics(user_id)


# ─── LinkedIn OAuth & Auto-Posting ────────────────────────────────

from fastapi.responses import RedirectResponse
from services.linkedin_api import linkedin_service

@app.get("/api/linkedin/auth")
async def linkedin_auth():
    """Redirect user to LinkedIn for authorization."""
    if not linkedin_service.client_id:
        raise HTTPException(
            status_code=400,
            detail="LinkedIn Client ID not configured. Add LINKEDIN_CLIENT_ID to .env. "
                   "Go to linkedin.com/developers/apps to create an app.",
        )
    url = linkedin_service.get_auth_url()
    return RedirectResponse(url=url)

@app.get("/api/linkedin/callback")
async def linkedin_callback(code: str = "", error: str = ""):
    """Handle OAuth callback — exchanges code for tokens, redirects to frontend."""
    if error:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}#settings?linkedin_error={error}")
    if not code:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}#settings?linkedin_error=no_code")

    try:
        token_data = await linkedin_service.exchange_code_for_token(code)
        # Redirect back to frontend Settings tab with success
        return RedirectResponse(url=f"{settings.FRONTEND_URL}#settings?linkedin=connected")
    except Exception as e:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}#settings?linkedin_error={str(e)[:100]}")

@app.get("/api/linkedin/status")
async def linkedin_status():
    """Check LinkedIn connection status with token health."""
    return await linkedin_service.get_status()

class LinkedInPostRequest(BaseModel):
    content: str = ""
    post_id: str = ""

@app.post("/api/linkedin/post")
async def publish_to_linkedin(req: LinkedInPostRequest):
    """Publish a post to your personal LinkedIn profile."""
    content = req.content
    post_id = req.post_id
    post = None

    if post_id:
        post = database.get_post(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]

    if not content:
        raise HTTPException(status_code=400, detail="Provide post_id or content")

    # If a card was rendered for this post, publish it with the post. Without
    # this, an image generated in the Editor was simply left behind.
    image_path = ""
    if post_id:
        images = database.get_post_images(post_id)
        if images and _Path(images[0].get("file_path", "")).exists():
            image_path = images[0]["file_path"]

    # Publish FIRST, then update status only on success
    if image_path:
        result = await linkedin_service.create_image_post(
            content, image_path, alt_text=(post or {}).get("title", "")
        )
        if result["status"] == "failed":
            # An upload problem should not block the post itself.
            logger.warning(
                f"Image post failed ({result.get('message')}) — publishing text only"
            )
            result = await linkedin_service.create_text_post(content)
    else:
        result = await linkedin_service.create_text_post(content)

    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result.get("message", "Posting failed"))

    # Only mark as published after confirmed success
    if post_id:
        database.update_post(post_id, status="published")

    return result



# ─── Post Images ──────────────────────────────────────────────────

from fastapi.responses import FileResponse
from pathlib import Path as _Path

from services import image_templates
from services.image_renderer import image_renderer, media_dir, RendererUnavailable
from services import image_pipeline
from services.image_style import image_style_analyzer
from services.visual_agent import visual_agent, infer_archetype

# Handles suggested on first run — the user edits these in the Images tab.
STARTER_HANDLES = [
    "@BugWhisperer",
    "@NullPointerKing",
    "@SemicolonHero",
    "@WorksOnMyBox",
    "@DeployAndPray",
    "@CacheMeOutside",
    "@GitPushHope",
]

_ALLOWED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _safe_media_path(stored: str) -> _Path:
    """Resolve a stored path, refusing anything outside the media directory."""
    root = media_dir().resolve()
    candidate = _Path(stored)
    if not candidate.is_absolute():
        candidate = root / candidate.name
    candidate = candidate.resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=400, detail="Invalid media path")
    return candidate


async def _store_upload(file: UploadFile, prefix: str) -> _Path:
    suffix = _Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Use one of: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image is larger than 10 MB")

    path = media_dir() / f"{prefix}_{uuid.uuid4().hex[:10]}{suffix}"
    path.write_bytes(data)
    return path


@app.get("/api/scheduler/status")
async def scheduler_status(user_id: str = "default"):
    """Why autonomous mode did or didn't post.

    Runs the same evaluation the scheduler uses, so this can never disagree
    with the real behaviour.
    """
    from services import scheduler as sched

    prefs = database.get_preferences(user_id)
    decision = sched.evaluate(prefs)
    ticks = database.list_scheduler_ticks(user_id, limit=30)
    return {
        **decision,
        "job": sched.scheduler_info(),
        "last_tick": sched.last_tick(),
        # The tick history makes a missed slot explainable: the scheduler only
        # runs while this backend is up, so a gap means it was not running.
        "recent_ticks": ticks,
        "linkedin_connected": bool(database.get_linkedin_token(user_id)),
    }


@app.get("/api/images/config")
async def get_image_config():
    """Archetypes and defaults the Images tab needs to render its controls."""
    return {
        "archetypes": [
            {"id": "social-card", "label": "Social card",
             "description": "Avatar, name, handle, then a question"},
            {"id": "interview-card", "label": "Interview card",
             "description": "Series badge, coloured title, highlights, CTA footer"},
            {"id": "code-card", "label": "Code card",
             "description": "Syntax-highlighted snippet in a window frame"},
            {"id": "diagram", "label": "Diagram",
             "description": "Architecture or flow, drawn from Mermaid"},
        ],
        "starter_handles": STARTER_HANDLES,
        "default_style": image_templates.DEFAULT_STYLE,
    }


@app.get("/api/images/identity")
async def get_image_identity(user_id: str = "default"):
    """Identity plus handle pool used on generated cards."""
    identity = database.get_image_identity(user_id)
    identity["avatar_url"] = (
        f"/api/images/file/{_Path(identity['avatar_path']).name}"
        if identity.get("avatar_path")
        else ""
    )
    return {"identity": identity, "handles": database.list_image_handles(user_id)}


class ImageIdentityUpdate(BaseModel):
    display_name: Optional[str] = None
    headline: Optional[str] = None
    verified: Optional[bool] = None
    verified_color: Optional[str] = None
    handle_strategy: Optional[str] = None
    user_id: str = "default"


@app.put("/api/images/identity")
async def update_image_identity(req: ImageIdentityUpdate):
    """Update the name, headline, badge and rotation strategy."""
    fields = req.model_dump(exclude={"user_id"}, exclude_none=True)
    return database.update_image_identity(req.user_id, **fields)


@app.post("/api/images/avatar")
async def upload_avatar(file: UploadFile = File(...), user_id: str = Form("default")):
    """Upload the profile photo shown on cards."""
    previous = database.get_image_identity(user_id).get("avatar_path", "")
    path = await _store_upload(file, "avatar")
    database.update_image_identity(user_id, avatar_path=str(path))

    if previous:
        try:
            _safe_media_path(previous).unlink(missing_ok=True)
        except (HTTPException, OSError):
            pass

    return {"avatar_url": f"/api/images/file/{path.name}", "message": "Avatar updated"}


class HandleCreate(BaseModel):
    handle: str
    user_id: str = "default"


@app.post("/api/images/handles")
async def add_image_handle(req: HandleCreate):
    """Add one handle to the rotation pool."""
    if not req.handle.strip():
        raise HTTPException(status_code=400, detail="Handle cannot be empty")
    result = database.add_image_handle(
        f"hdl_{uuid.uuid4().hex[:10]}", req.handle, req.user_id
    )
    if result["duplicate"]:
        return {**result, "message": f"{result['handle']} is already in the pool"}
    return {**result, "message": f"Added {result['handle']}"}


@app.post("/api/images/handles/seed")
async def seed_image_handles(user_id: str = "default"):
    """Populate the pool with the starter handles, skipping any that exist."""
    added = 0
    for handle in STARTER_HANDLES:
        if not database.add_image_handle(f"hdl_{uuid.uuid4().hex[:10]}", handle, user_id)["duplicate"]:
            added += 1
    return {"added": added, "message": f"{added} handles added"}


@app.put("/api/images/handles/{handle_id}")
async def toggle_image_handle(handle_id: str, enabled: bool = True):
    """Enable or disable a handle without deleting it."""
    if not database.set_image_handle_enabled(handle_id, enabled):
        raise HTTPException(status_code=404, detail="Handle not found")
    return {"id": handle_id, "enabled": enabled}


@app.delete("/api/images/handles/{handle_id}")
async def delete_image_handle(handle_id: str):
    if not database.delete_image_handle(handle_id):
        raise HTTPException(status_code=404, detail="Handle not found")
    return {"deleted": True, "id": handle_id}


@app.get("/api/images/presets")
async def list_image_presets(user_id: str = "default", archetype: str = None):
    """Style presets extracted from uploaded inspiration images."""
    presets = database.list_image_presets(user_id, archetype)
    for preset in presets:
        preset["source_url"] = (
            f"/api/images/file/{_Path(preset['source_image']).name}"
            if preset.get("source_image")
            else ""
        )
    return {"presets": presets, "total": len(presets)}


@app.post("/api/images/inspiration")
async def upload_inspiration_image(
    file: UploadFile = File(...), user_id: str = Form("default"),
):
    """Upload a reference image and extract a reusable style preset.

    The vision model runs once, here. Generation later reads the stored preset
    rather than looking at the image again.
    """
    path = await _store_upload(file, "inspo")

    try:
        analysis = await image_style_analyzer.analyze(str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not analyse image: {str(e)[:200]}")

    preset_id = f"preset_{uuid.uuid4().hex[:10]}"
    database.add_image_preset(
        preset_id=preset_id,
        archetype=analysis["archetype"],
        style=analysis["style"],
        name=analysis.get("name") or analysis["archetype"],
        source_image=str(path),
        user_id=user_id,
    )

    return {
        "id": preset_id,
        "archetype": analysis["archetype"],
        "name": analysis.get("name", ""),
        "style": analysis["style"],
        "source_url": f"/api/images/file/{path.name}",
        "warning": analysis.get("warning", ""),
        "message": f"Style learned as {analysis['archetype']}",
    }


@app.delete("/api/images/presets/{preset_id}")
async def delete_image_preset(preset_id: str):
    preset = database.delete_image_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    if preset.get("source_image"):
        try:
            _safe_media_path(preset["source_image"]).unlink(missing_ok=True)
        except (HTTPException, OSError):
            pass
    return {"deleted": True, "id": preset_id}


class ImageGenerateRequest(BaseModel):
    post_id: str = ""
    content: str = ""
    archetype: str = ""        # blank lets the agent choose
    preset_id: str = ""        # blank picks a preset matching the archetype
    handle: str = ""           # blank draws the next one from the pool
    payload: Optional[dict] = None  # supply to skip the writing step
    user_id: str = "default"


@app.post("/api/images/generate")
async def generate_post_image(req: ImageGenerateRequest):
    """Render an image for a post.

    With no archetype or payload the agent decides and writes the content;
    supply either to override it from the Editor.
    """
    content = req.content
    if req.post_id and not content:
        post = database.get_post(req.post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]
    if not content and not req.payload:
        raise HTTPException(status_code=400, detail="Provide post_id, content, or payload")

    archetype = req.archetype
    payload = req.payload or {}
    reason = ""

    if not payload:
        if not archetype:
            decision = await visual_agent.decide(content, "", "")
            if not decision["needs_image"]:
                return {
                    "generated": False,
                    "reason": decision["reason"],
                    "message": "No image — " + (decision["reason"] or "not a good fit"),
                }
            archetype = decision["archetype"]
            reason = decision["reason"]
        try:
            payload = await visual_agent.write_payload(content, archetype)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e)[:300])

    # A payload can arrive without its archetype (the Editor forwards a saved
    # payload but leaves archetype blank). Recover it from the payload's shape
    # so a diagram payload isn't rendered through the social-card template.
    if not archetype:
        archetype = infer_archetype(payload)

    archetype = archetype or "social-card"

    # Same code path the scheduler uses, so an auto-published post is rendered
    # with the same preset, handle rotation and identity as a manual one.
    try:
        record = await image_pipeline.render_for_post(
            archetype=archetype,
            payload=payload,
            user_id=req.user_id,
            post_id=req.post_id,
            preset_id=req.preset_id,
            handle=req.handle,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Preset not found")
    except RendererUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {str(e)[:300]}")

    return {
        "generated": True,
        "id": record["id"],
        "archetype": record["archetype"],
        "handle": record["handle"],
        "preset_id": record["preset_id"],
        "payload": record["payload"],
        "reason": reason,
        "url": record["url"],
        "message": f"{record['archetype']} generated",
    }


@app.get("/api/images/post/{post_id}")
async def list_images_for_post(post_id: str):
    images = database.get_post_images(post_id)
    for img in images:
        img["url"] = f"/api/images/file/{_Path(img['file_path']).name}"
    return {"images": images, "total": len(images)}


@app.delete("/api/images/{image_id}")
async def delete_generated_image(image_id: str):
    image = database.delete_post_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        _safe_media_path(image["file_path"]).unlink(missing_ok=True)
    except (HTTPException, OSError):
        pass
    return {"deleted": True, "id": image_id}


@app.get("/api/images/file/{filename}")
async def serve_media_file(filename: str):
    """Serve a generated image, avatar, or inspiration reference."""
    # Only bare filenames inside the media directory are addressable.
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _safe_media_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
