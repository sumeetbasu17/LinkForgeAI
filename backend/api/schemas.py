"""
Pydantic schemas for API request/response models.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─── Generation ───────────────────────────────────────────────────

class GeneratePostRequest(BaseModel):
    category: str = Field(..., description="Category ID like 'ai-engineering'")
    topic: str = Field("", description="Optional specific topic. AI picks if empty.")
    # Blank means "use my settings". Anything sent here wins over settings.
    format: str = Field("", description="Post format: story, listicle, hot-take, tutorial, reflection, trend. Blank uses default_format from preferences.")
    tone: str = Field("", description="Tone: Professional, Conversational, etc. Blank uses the category's tone override, then default_tone.")
    user_id: str = Field("default", description="User identifier")


class GeneratePostResponse(BaseModel):
    post_id: str
    title: str
    content: str
    category: str
    format: str
    tone: str
    style_score: float
    status: str
    research_summary: str = ""
    selected_topic: str = ""
    revision_count: int = 0

    # Visual suggestion from the decide_visual node. The image is not rendered
    # during generation — the Editor calls /api/images/generate so the user can
    # accept, change, or drop it first.
    wants_image: bool = False
    image_archetype: str = ""
    image_reason: str = ""
    image_payload: dict = {}


# ─── Posts CRUD ───────────────────────────────────────────────────

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    category: Optional[str] = None
    format: Optional[str] = None
    tone: Optional[str] = None


class PostResponse(BaseModel):
    id: str
    title: str
    content: str
    category: str
    format: str
    tone: str
    status: str
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    impressions: int = 0
    style_score: Optional[float] = None
    created_at: str
    updated_at: str


# ─── Style Posts ──────────────────────────────────────────────────

class AddStylePostRequest(BaseModel):
    content: str = Field(..., description="Post text content")
    post_type: str = Field("own", description="'own' for your posts, 'inspiration' for others'")
    category: str = Field("", description="Optional category")
    source_url: str = Field("", description="Optional source URL for inspiration posts")
    user_id: str = Field("default")


class SplitPreviewRequest(BaseModel):
    content: str = Field(..., description="Pasted text that may hold several posts")


class AddStylePostsBulkRequest(BaseModel):
    """Add several style posts at once, e.g. after splitting a paste."""

    contents: list[str] = Field(..., description="One entry per post")
    post_type: str = Field("own", description="'own', 'inspiration' or 'comment'")
    category: str = Field("", description="Blank means auto-detect per post")
    source_url: str = Field("", description="Optional source URL")
    user_id: str = Field("default")


class StylePostResponse(BaseModel):
    id: str
    content: str
    post_type: str
    category: str
    message: str = ""


# ─── Preferences ──────────────────────────────────────────────────

class PreferencesUpdate(BaseModel):
    active_categories: Optional[list[str]] = None
    tone_overrides: Optional[dict[str, str]] = None
    default_tone: Optional[str] = None
    default_format: Optional[str] = None
    posting_frequency: Optional[int] = None
    preferred_days: Optional[list[str]] = None
    preferred_time: Optional[str] = None
    auto_post_enabled: Optional[bool] = None


class PreferencesResponse(BaseModel):
    user_id: str
    active_categories: list[str]
    tone_overrides: dict
    default_tone: str
    default_format: str
    posting_frequency: int
    preferred_days: list[str]
    preferred_time: str
    auto_post_enabled: bool = False
    style_profile: dict = {}


# ─── Config ───────────────────────────────────────────────────────

class ConfigResponse(BaseModel):
    categories: list[dict]
    formats: list[dict]
    tones: list[str]


# ─── Style Analysis ──────────────────────────────────────────────

class AnalyzeStyleRequest(BaseModel):
    user_id: str = "default"


class StyleProfileResponse(BaseModel):
    avg_word_count: int = 0
    avg_paragraph_count: int = 0
    uses_code_blocks: bool = False
    uses_arrow_bullets: bool = False
    hook_style: str = ""
    cta_style: str = ""
    formatting_style: str = ""
    voice_description: str = ""
    tone_keywords: list[str] = []
    emoji_style: str = ""
    post_count: int = 0
