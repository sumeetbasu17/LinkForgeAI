"""
Node functions for the LangGraph post generation pipeline.
Each function receives and returns a dict (PostGenerationState).

Node 1: load_style_context — loads user style from vector DB (no LLM)
Node 2: select_topic       — LLM (light) picks a topic
Node 3: research           — Tavily API fetches facts (no LLM)
Node 4: draft_post         — LLM (heavy) writes the post
Node 5: quality_check      — vector similarity + optional LLM scoring
"""

from agents.state import PostGenerationState
from services.llm import llm_service
from services.research import research_service
from db.vector_store import vector_store
from db.database import database
from config.settings import settings


async def load_style_context(state: PostGenerationState) -> dict:
    """Load user's style profile and similar posts from vector DB."""
    updates = {"status": "generating"}

    prefs = database.get_preferences(state["user_id"])
    style_data = prefs.get("style_profile", {})
    if isinstance(style_data, dict) and style_data:
        parts = [f"{k}: {v}" for k, v in style_data.items() if v and v not in ("", "0", 0, [], {})]
        updates["style_profile"] = "\n".join(parts) if parts else ""

    # Load custom rules
    custom_rules = prefs.get("custom_rules", "")
    if custom_rules:
        updates["custom_rules"] = custom_rules

    search_text = state.get("topic") or state.get("category") or ""
    if search_text:
        similar = vector_store.find_similar_posts(
            content=search_text, user_id=state["user_id"], post_type="own", limit=3,
        )
        updates["similar_past_posts"] = [s["content"] for s in similar]

        inspiration = vector_store.find_similar_posts(
            content=search_text, user_id=state["user_id"], post_type="inspiration", limit=2,
        )
        updates["inspiration_structures"] = [s["content"] for s in inspiration]

    return updates


async def select_topic(state: PostGenerationState) -> dict:
    """LLM (light) picks the best topic from trends, avoiding repeats."""

    category_info = None
    for cat in settings.DEFAULT_CATEGORIES:
        if cat["id"] == state.get("category"):
            category_info = cat
            break

    cat_label = category_info["label"] if category_info else state.get("category", "")
    cat_desc = category_info.get("description", "") if category_info else ""

    # If user provided a specific topic, use it
    if state.get("topic") and len(state["topic"]) > 10:
        return {"selected_topic": state["topic"], "topic_reasoning": "User-provided topic"}

    # Fetch trending topics
    try:
        trending = await research_service.find_trending_topics(cat_label, cat_desc)
    except Exception:
        trending = []

    recent_titles = database.get_recent_post_titles(state.get("user_id", "default"), limit=15)

    trending_text = "\n".join([f"- {t['title']}: {t['summary'][:150]}" for t in trending[:8]])
    recent_text = "\n".join([f"- {t}" for t in recent_titles]) if recent_titles else "No previous posts."

    system_prompt = """You are a LinkedIn content strategist for senior software engineers.
Pick the single best topic for a LinkedIn post. It should be timely and engaging."""

    user_prompt = f"""Category: {cat_label}
Focus: {cat_desc}
Format: {state.get('format', 'story')}

Trending topics:
{trending_text or "No trending data. Suggest an evergreen topic."}

Already written (AVOID these):
{recent_text}

{f"User hint: {state.get('topic')}" if state.get('topic') else ""}

Return JSON: {{"topic": "specific topic title", "reasoning": "why (1 sentence)"}}"""

    try:
        result = await llm_service.call_structured(system_prompt, user_prompt, light=True)
        return {
            "selected_topic": result.get("topic", f"Latest in {cat_label}"),
            "topic_reasoning": result.get("reasoning", ""),
        }
    except Exception:
        if trending:
            return {"selected_topic": trending[0]["title"], "topic_reasoning": "Top trending (LLM fallback)"}
        return {"selected_topic": state.get("topic") or f"Key insights in {cat_label}", "topic_reasoning": "Default topic"}


async def research(state: PostGenerationState) -> dict:
    """Tavily API fetches facts. No LLM needed."""
    try:
        result = await research_service.research_topic(state.get("selected_topic", ""))
        return {
            "research_facts": result.get("facts", []),
            "research_summary": result.get("answer", ""),
        }
    except Exception:
        return {"research_facts": [], "research_summary": "Research unavailable; using general knowledge."}


async def draft_post(state: PostGenerationState) -> dict:
    """LLM (heavy) writes the post using research + style + past posts."""

    research_ctx = ""
    if state.get("research_facts"):
        facts = "\n".join([f"- {f['source']}: {f['content'][:200]}" for f in state["research_facts"][:5]])
        research_ctx = f"\n## Recent research:\n{state.get('research_summary', '')}\n\nFacts:\n{facts}\n"

    style_ctx = ""
    if state.get("style_profile"):
        style_ctx = f"\n## User's writing style:\n{state['style_profile']}\n"

    past_ctx = ""
    if state.get("similar_past_posts"):
        posts = "\n\n---\n\n".join(state["similar_past_posts"][:2])
        past_ctx = f"\n## User's past posts (match this voice):\n{posts}\n"

    insp_ctx = ""
    if state.get("inspiration_structures"):
        structs = "\n\n---\n\n".join(state["inspiration_structures"][:2])
        insp_ctx = f"\n## Structural inspiration (use structure, NOT content):\n{structs}\n"

    revision_ctx = ""
    if state.get("revision_count", 0) > 0 and state.get("quality_feedback"):
        revision_ctx = f"\n## REVISION — Previous scored {state.get('style_score', 0)}/100\nFeedback: {state['quality_feedback']}\nPrevious draft:\n{state.get('draft_content', '')}\n"

    rules_ctx = ""
    if state.get("custom_rules"):
        rules_ctx = f"\n## IMPORTANT USER RULES (follow these strictly):\n{state['custom_rules']}\n"

    system_prompt = f"""You are a LinkedIn ghostwriter for a Senior Software Development Engineer
with 12+ years of experience.

NEVER INVENT THE AUTHOR'S EXPERIENCE. This is the rule that matters most.
You do not know what this person did last week, what they shipped, who they
work for, what their team decided, or what results they measured. Writing
"I ripped out X last week and shipped 3x faster" when it never happened puts a
fabricated claim under their real name in front of their colleagues.

So do not write:
- invented incidents ("Last week I...", "A junior on my team asked me...")
- invented metrics ("shipped 3x faster", "cut latency by 40%", "200 lines")
- invented employers, projects, teams, timelines, or conversations

The ONLY personal experience you may reference is what actually appears in the
user's past posts shown below. Everything else must be framed as observation,
analysis, or a general pattern. Use framings like:
- "A pattern I keep seeing in production systems..."
- "Teams often reach for X when Y would do."
- "If you've ever debugged this, you know..."
- "Here's what actually happens when..."

Claims about the technology itself should be true and current. Any figure you
cite must come from the research section below and be attributed there.

FORMATTING:
1. Write ONLY the post content. No titles, no metadata, no preamble.
2. NO markdown. LinkedIn renders it literally, so **bold** appears as asterisks
   on screen. For emphasis use line breaks, capitals sparingly, or "→".
3. Short paragraphs with line breaks between them.
4. NO external links — LinkedIn suppresses reach on them.

CRAFT:
5. Open with a hook in the first two lines; that is the "see more" cut-off.
6. Match the user's writing style if one is provided.
7. Prefer a concrete technical example, a comparison, or real code over a story.
8. End with a question or CTA that invites a genuine answer.
9. Add 3-4 hashtags at the end, only where they aid discovery.
10. Keep under 250 words.
11. Write as a peer, not a teacher."""

    # "Story" is the format most likely to tip the model into inventing an
    # anecdote, so it gets an explicit reminder of where a story may come from.
    format_ctx = ""
    if state.get("format") in ("story", "reflection"):
        format_ctx = (
            "\n## Note on this format:\n"
            "A story or reflection must be built from the user's past posts above, "
            "or told as a general pattern observed across teams. If you have no real "
            "material for a first-person narrative, write it as analysis instead — "
            "that is always better than inventing an incident.\n"
        )

    user_prompt = f"""Topic: {state.get('selected_topic', '')}
Category: {state.get('category', '')}
Format: {state.get('format', 'story')}
Tone: {state.get('tone', 'Conversational')}
{research_ctx}{style_ctx}{past_ctx}{insp_ctx}{format_ctx}{rules_ctx}{revision_ctx}
Write the post now. Every factual claim must be either true of the technology or
drawn from the material above. Invent nothing about the author."""

    try:
        content = await llm_service.call_heavy(system_prompt, user_prompt)
        title_result = await llm_service.call_structured(
            "Generate a short title (5-8 words) for this post. Return JSON: {\"title\": \"...\"}",
            f"Post:\n{content[:300]}", light=True,
        )
        return {
            "draft_content": content.strip(),
            "draft_title": title_result.get("title", state.get("selected_topic", "Untitled")[:60]),
        }
    except Exception as e:
        return {"error": f"Draft failed: {str(e)}", "status": "failed"}


async def quality_check(state: PostGenerationState) -> dict:
    """Vector similarity + optional LLM scoring."""
    if state.get("status") == "failed":
        return {}

    # Vector similarity
    style_score = vector_store.compute_style_similarity(
        draft=state.get("draft_content", ""), user_id=state.get("user_id", "default"),
    )
    updates = {"style_score": style_score}

    # If low score and revisions remaining, get LLM feedback
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    if style_score < 70 and revision_count < max_revisions:
        try:
            feedback = await llm_service.call_structured(
                "You review LinkedIn posts. Score and give actionable feedback.",
                f"""Draft:\n{state.get('draft_content', '')}\n\nStyle profile:\n{state.get('style_profile', 'None')}\n\nReturn JSON: {{"score": 0-100, "feedback": "2-3 sentences", "passes": true/false}}""",
                light=True,
            )
            llm_score = feedback.get("score", 75)
            updates["style_score"] = (style_score * 0.4) + (llm_score * 0.6)
            updates["quality_feedback"] = feedback.get("feedback", "")

            if not feedback.get("passes", True):
                updates["revision_count"] = revision_count + 1
                return updates
        except Exception:
            pass

    # Post passes
    updates["final_post"] = state.get("draft_content", "")
    updates["final_title"] = state.get("draft_title", "")
    updates["status"] = "completed"
    return updates


async def decide_visual(state: PostGenerationState) -> dict:
    """Judge whether the finished post deserves an image, and write its content.

    Runs after the post is final so the decision is made on what was actually
    written. Never fails the pipeline — a post without an image is fine, a
    pipeline that dies trying to make one is not.
    """
    if state.get("status") == "failed":
        return {}

    post = state.get("final_post") or state.get("draft_content", "")
    if not post:
        return {}

    from services.visual_agent import visual_agent

    try:
        plan = await visual_agent.plan(
            post, state.get("category", ""), state.get("format", "")
        )
    except Exception as exc:
        return {"wants_image": False, "image_reason": f"Visual step skipped: {str(exc)[:150]}"}

    return {
        "wants_image": plan.get("needs_image", False),
        "image_archetype": plan.get("archetype", ""),
        "image_reason": plan.get("reason", ""),
        "image_payload": plan.get("payload", {}),
    }


def should_revise(state: PostGenerationState) -> str:
    """Conditional edge: 'revise' or 'finalize'."""
    if state.get("status") == "failed":
        return "finalize"
    if state.get("status") == "completed":
        return "finalize"
    if state.get("style_score", 100) < 70 and state.get("revision_count", 0) <= state.get("max_revisions", 2):
        if not state.get("final_post"):
            return "revise"
    return "finalize"
