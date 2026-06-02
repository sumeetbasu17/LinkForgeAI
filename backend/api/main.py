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
    """Generate a new LinkedIn post using the LangGraph agent pipeline."""

    # Check for tone override
    prefs = database.get_preferences(req.user_id)
    tone = req.tone
    tone_overrides = prefs.get("tone_overrides", {})
    if req.category in tone_overrides:
        tone = tone_overrides[req.category]

    # Run the agent pipeline
    result = await generate_post(
        user_id=req.user_id,
        category=req.category,
        topic=req.topic,
        format=req.format,
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
        format=req.format,
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
      - .txt: Articles separated by blank lines, '---', or 'Article N :' headers
      - .csv: Columns 'content', optional 'category', 'url'
      - .json: Array of {"content": "...", "category": "...", "url": "..."}
      - .pdf: Extracts text, splits into articles by page breaks or blank lines

    If category is empty (Auto-detect), each article is classified by AI.
    If category is set, ALL articles get that category.
    """
    import re

    content_bytes = await file.read()
    filename = (file.filename or "").lower()
    added = 0
    auto_detected = 0
    use_auto = not category

    parsed_articles = []

    # ─── PDF ──────────────────────────────────────────────────
    if filename.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            doc_pdf = fitz.open(stream=content_bytes, filetype="pdf")
            full_text = ""
            for page in doc_pdf:
                full_text += page.get_text() + "\n\n---PAGE_BREAK---\n\n"
            doc_pdf.close()

            # Split by page breaks first, then by large gaps
            pages = full_text.split("---PAGE_BREAK---")
            for page_text in pages:
                articles_in_page = _split_text_into_articles(page_text)
                for art in articles_in_page:
                    parsed_articles.append(art)

        except ImportError:
            raise HTTPException(
                status_code=400,
                detail="PDF support requires pymupdf. Run: pip install pymupdf"
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {str(e)[:200]}")

    # ─── JSON ─────────────────────────────────────────────────
    elif filename.endswith(".json"):
        import json as json_mod
        text = content_bytes.decode("utf-8", errors="ignore")
        try:
            articles = json_mod.loads(text)
            if not isinstance(articles, list):
                articles = [articles]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON file")

        for art in articles:
            if isinstance(art, str):
                art = {"content": art}
            art_content = art.get("content", "").strip()
            if art_content and len(art_content) >= 20:
                parsed_articles.append({
                    "content": art_content,
                    "category": art.get("category", ""),
                    "url": art.get("url", ""),
                })

    # ─── CSV ──────────────────────────────────────────────────
    elif filename.endswith(".csv"):
        import csv, io
        text = content_bytes.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            art_content = row.get("content", "").strip()
            if art_content and len(art_content) >= 20:
                parsed_articles.append({
                    "content": art_content,
                    "category": row.get("category", ""),
                    "url": row.get("url", ""),
                })

    # ─── Plain text (.txt or anything else) ───────────────────
    else:
        text = content_bytes.decode("utf-8", errors="ignore")
        parsed_articles = _split_text_into_articles(text)

    if not parsed_articles:
        raise HTTPException(status_code=400, detail="No valid articles found (minimum 20 characters each)")

    # Auto-categorize if needed
    if use_auto and parsed_articles:
        contents = [a["content"] for a in parsed_articles]
        cats = await auto_categorizer.categorize_batch(contents)
        for i, cat in enumerate(cats):
            if i < len(parsed_articles) and not parsed_articles[i]["category"]:
                parsed_articles[i]["category"] = cat
                if cat:
                    auto_detected += 1

    # Save all
    for art in parsed_articles:
        pid = f"style_{uuid.uuid4().hex[:12]}"
        art_cat = art["category"] or category
        database.add_style_post(pid, art["content"], post_type, user_id, art_cat, art.get("url", ""))
        vector_store.add_post(user_id, art["content"], art_cat, post_type, pid)
        added += 1

    result = {"added": added, "post_type": post_type}
    if use_auto:
        result["auto_categorized"] = auto_detected
        result["message"] = f"{added} articles imported, {auto_detected} auto-categorized"
    else:
        result["category"] = category
        result["message"] = f"{added} articles imported to {category}"
    return result


def _split_text_into_articles(text: str) -> list[dict]:
    """Smart article splitter. Handles multiple separator styles:

    1. 'Article N :' or 'Article N:' headers
    2. '---' separator lines
    3. 3+ consecutive blank lines (articles just stacked with gaps)
    4. LinkedIn URL as article boundary (URL at end = article ends there)

    Returns list of {"content": str, "category": str, "url": str}
    """
    import re

    # First, check if text uses explicit separators
    has_article_headers = bool(re.search(r'Article\s+\d+\s*:', text, re.IGNORECASE))
    has_dashes = bool(re.search(r'\n---+\n', text))

    if has_article_headers:
        parts = re.split(r'\n*Article\s+\d+\s*:\s*', text, flags=re.IGNORECASE)
    elif has_dashes:
        parts = re.split(r'\n---+\n', text)
    else:
        # No explicit separators — split by 3+ blank lines
        # This handles "articles stacked with empty lines between them"
        parts = re.split(r'\n\s*\n\s*\n\s*\n', text)

        # If that only gives 1 chunk, try splitting by LinkedIn URLs
        # (URL at end of article acts as boundary)
        if len(parts) <= 1:
            parts = re.split(
                r'(https?://(?:www\.)?linkedin\.com/\S+)',
                text
            )
            # Re-merge: content + URL pairs
            merged = []
            i = 0
            while i < len(parts):
                content = parts[i].strip()
                url = ""
                if i + 1 < len(parts) and parts[i + 1].startswith("http"):
                    url = parts[i + 1].strip()
                    i += 2
                else:
                    i += 1
                if content and len(content) >= 20:
                    merged.append({"content": content, "category": "", "url": url})
            return merged

    # Process parts — extract URLs from end of each
    articles = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 20:
            continue

        # Extract LinkedIn URL if present at end
        url = ""
        url_match = re.search(r'\s*(https?://\S+)\s*$', part)
        if url_match:
            url = url_match.group(1).strip()
            part = part[:url_match.start()].strip()

        if part and len(part) >= 20:
            articles.append({"content": part, "category": "", "url": url})

    return articles


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

    if post_id:
        post = database.get_post(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        content = post["content"]

    if not content:
        raise HTTPException(status_code=400, detail="Provide post_id or content")

    # Publish FIRST, then update status only on success
    result = await linkedin_service.create_text_post(content)

    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result.get("message", "Posting failed"))

    # Only mark as published after confirmed success
    if post_id:
        database.update_post(post_id, status="published")

    return result


