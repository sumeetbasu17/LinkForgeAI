"""
Agent state schema for the LangGraph post generation pipeline.
Uses TypedDict as required by LangGraph's StateGraph.
"""

from typing import TypedDict


class PostGenerationState(TypedDict, total=False):
    """State that flows through the LangGraph pipeline."""

    # Input
    user_id: str
    category: str
    topic: str
    format: str
    tone: str

    # Topic Selection
    selected_topic: str
    topic_reasoning: str

    # Research
    research_facts: list
    research_summary: str

    # Draft
    draft_content: str
    draft_title: str

    # Quality Check
    style_score: float
    quality_feedback: str
    revision_count: int
    max_revisions: int

    # Style context
    style_profile: str
    similar_past_posts: list
    inspiration_structures: list
    custom_rules: str

    # Visual
    wants_image: bool
    image_archetype: str
    image_reason: str
    image_payload: dict

    # Output
    final_post: str
    final_title: str
    status: str
    error: str


def make_initial_state(
    user_id: str = "default",
    category: str = "",
    topic: str = "",
    format: str = "story",
    tone: str = "Conversational",
) -> PostGenerationState:
    """Create a properly initialized state dict."""
    return PostGenerationState(
        user_id=user_id,
        category=category,
        topic=topic,
        format=format,
        tone=tone,
        selected_topic="",
        topic_reasoning="",
        research_facts=[],
        research_summary="",
        draft_content="",
        draft_title="",
        style_score=0.0,
        quality_feedback="",
        revision_count=0,
        max_revisions=2,
        style_profile="",
        similar_past_posts=[],
        inspiration_structures=[],
        custom_rules="",
        wants_image=False,
        image_archetype="",
        image_reason="",
        image_payload={},
        final_post="",
        final_title="",
        status="pending",
        error="",
    )
