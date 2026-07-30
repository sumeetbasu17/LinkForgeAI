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


def _category_query(category: str) -> str:
    """Turn a category id into words worth searching for.

    Retrieval used to run on the raw id ("ai-engineering"), which matches very
    little. The label and description are what the posts are actually about.
    """
    for cat in settings.DEFAULT_CATEGORIES:
        if cat["id"] == category:
            return " ".join(
                filter(None, [cat.get("label", ""), cat.get("description", "")])
            )
    return (category or "").replace("-", " ")


def _search(user_id: str, query: str, post_type: str, category: str, limit: int) -> list[str]:
    """Search one post type, preferring the post's own category.

    The style library is organised by category — 76 inspiration posts under
    system-design, 47 under ai-engineering and so on — so a post about system
    design should be shaped by the system-design shelf, not by whatever the
    embedding happened to rank highest across every category. If that shelf is
    thin (genai-tools has a single own post), the remainder is topped up from
    the whole library rather than returning less material.
    """
    found: list[str] = []
    seen: set[str] = set()

    for cat in ([category] if category else []) + [None]:
        if len(found) >= limit:
            break
        try:
            hits = vector_store.find_similar_posts(
                content=query,
                user_id=user_id,
                post_type=post_type,
                category=cat,
                limit=limit,
            )
        except Exception:
            continue
        for hit in hits:
            content = hit.get("content", "")
            key = content[:200]
            if content and key not in seen:
                seen.add(key)
                found.append(content)
            if len(found) >= limit:
                break
    return found


def _retrieve_examples(user_id: str, query: str, category: str = "") -> dict:
    """Pull the user's own posts and inspiration posts for a query.

    Both lists matter: "own" teaches voice, "inspiration" teaches which angles
    land in this category. Retrieval failures must never fail a generation, so
    they degrade to empty.
    """
    if not query:
        return {"similar_past_posts": [], "inspiration_structures": []}
    return {
        "similar_past_posts": _search(user_id, query, "own", category, 3),
        "inspiration_structures": _search(user_id, query, "inspiration", category, 3),
    }


def _profile_to_text(style_data: dict) -> str:
    if not isinstance(style_data, dict) or not style_data:
        return ""
    parts = [
        f"{k}: {v}"
        for k, v in style_data.items()
        if v and v not in ("", "0", 0, [], {})
    ]
    return "\n".join(parts)


async def load_style_context(state: PostGenerationState) -> dict:
    """Load the user's style profile, custom rules and example posts."""
    updates = {"status": "generating"}
    user_id = state["user_id"]

    prefs = database.get_preferences(user_id)
    profile_text = _profile_to_text(prefs.get("style_profile", {}))

    # A profile only exists once "Analyze my style" has been run. Without this
    # fallback a user with 70 uploaded posts still gets a style-blind prompt,
    # which is exactly how a post ends up sounding nothing like them.
    if not profile_text:
        own_posts = [
            p["content"]
            for p in database.get_style_posts(user_id=user_id, post_type="own")
        ]
        if own_posts:
            from services.style_analyzer import style_analyzer

            basic = style_analyzer.analyze_posts_basic(own_posts)
            profile_text = basic.to_prompt_string()
            # Cache it so the next run doesn't recompute, and so the Style tab
            # shows something instead of an empty profile.
            try:
                database.update_preferences(user_id, style_profile=basic.to_dict())
            except Exception:
                pass
    updates["style_profile"] = profile_text

    custom_rules = prefs.get("custom_rules", "") or ""
    if custom_rules.strip():
        updates["custom_rules"] = custom_rules.strip()

    category = state.get("category", "")
    query = state.get("topic") or _category_query(category)
    updates.update(_retrieve_examples(user_id, query, category))
    return updates


async def refresh_style_context(state: PostGenerationState) -> dict:
    """Re-retrieve examples once the real topic is known.

    The first pass runs before topic selection, so it can only search on the
    category. Now that a topic exists, search again on that — much closer to
    the post about to be written. Whatever comes back replaces the earlier
    guess, unless the new search returns nothing.
    """
    topic = (state.get("selected_topic") or "").strip()
    if not topic:
        return {}

    category = state.get("category", "")
    query = f"{topic} {_category_query(category)}".strip()
    found = _retrieve_examples(state["user_id"], query, category)
    updates = {}
    if found["similar_past_posts"]:
        updates["similar_past_posts"] = found["similar_past_posts"]
    if found["inspiration_structures"]:
        updates["inspiration_structures"] = found["inspiration_structures"]
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

    # Inspiration posts saved under this category are a second source of topics
    # next to live trends: they are the angles the user already decided were
    # worth learning from in this area.
    insp_text = ""
    inspiration = state.get("inspiration_structures") or []
    if inspiration:
        openers = []
        for post in inspiration[:3]:
            first = " ".join(post.strip().split())[:180]
            if first:
                openers.append(f"- {first}")
        insp_text = "\n".join(openers)

    system_prompt = """You are a LinkedIn content strategist for senior software engineers.
Pick the single best topic for a LinkedIn post. It should be timely and engaging.

You may pick a topic close to one of the saved inspiration posts — covering the
same ground in the author's own way is fine and often the point. What you must
not do is pick a topic the author has already written about recently."""

    user_prompt = f"""Category: {cat_label}
Focus: {cat_desc}
Format: {state.get('format', 'story')}

Trending topics:
{trending_text or "No trending data. Suggest an evergreen topic."}

Inspiration posts saved under this category (fair game to cover a similar
topic from the author's own angle):
{insp_text or "None saved."}

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
        posts = "\n\n---\n\n".join(state["similar_past_posts"][:3])
        past_ctx = (
            "\n## The user's own past posts — THIS is the voice to reproduce:\n"
            f"{posts}\n\n"
            "Match their sentence length, paragraph rhythm, punctuation habits and "
            "vocabulary. Do not imitate a generic LinkedIn voice.\n"
        )

    insp_ctx = ""
    if state.get("inspiration_structures"):
        structs = "\n\n---\n\n".join(state["inspiration_structures"][:3])
        insp_ctx = (
            "\n## Inspiration posts other authors wrote in this category:\n"
            f"{structs}\n\n"
            "Use these for the ANGLE and the SHAPE — how the idea is opened, how "
            "it is sequenced, where it lands. Covering the same subject is fine, "
            "and writing the author's own version of one of these is fine.\n"
            "What is not fine: reusing their sentences, their phrasing, their "
            "examples or their metrics. Rewrite from scratch in the author's "
            "voice as shown in their own posts above. If the result reads like "
            "the inspiration post with words swapped, start again.\n"
        )

    revision_ctx = ""
    if state.get("revision_count", 0) > 0 and state.get("quality_feedback"):
        revision_ctx = f"\n## REVISION — Previous scored {state.get('style_score', 0)}/100\nFeedback: {state['quality_feedback']}\nPrevious draft:\n{state.get('draft_content', '')}\n"

    # Custom rules belong in the SYSTEM prompt, not at the end of the user
    # message. Buried below research and examples they lost every conflict with
    # the defaults below (word count, hashtags, persona), which is why posts came
    # out off-voice despite the rules being saved.
    rules_ctx = ""
    rules_block = ""
    if state.get("custom_rules"):
        rules_ctx = (
            "\n## Before you write — the author's rules are the style spec:\n"
            "Your system instructions contain the author's own writing rules. "
            "They define the voice, structure, hooks, examples, length, endings "
            "and hashtags for this post. Write to those rules, not to a generic "
            "LinkedIn voice. After drafting, check the post against each rule and "
            "fix anything that drifts before returning it.\n"
        )
        rules_block = f"""

═══════════════════════════════════════════════════════════
THE AUTHOR'S OWN RULES — HIGHEST PRIORITY
These are written by the person whose name goes on this post. Where they
conflict with any craft or formatting guidance further down (length, hashtags,
structure, tone, openings, endings), THE AUTHOR'S RULES WIN. The only thing
they cannot override is the ban on inventing their experience.
═══════════════════════════════════════════════════════════
{state['custom_rules']}
═══════════════════════════════════════════════════════════
"""

    # Hard constraints are LinkedIn platform facts, not style — they apply no
    # matter what the author's rules say. Everything ELSE about craft is left to
    # the author's rules when they exist, so the persona isn't diluted by a
    # second, generic set of style instructions competing for the model's
    # attention.
    hard_constraints = """HARD CONSTRAINTS (platform facts, always apply):
- Write ONLY the post content. No title, no metadata, no preamble, no surrounding quotes.
- NO markdown. LinkedIn renders **bold** and ## as literal characters. Use line breaks, and "→" for emphasis.
- NO external links — LinkedIn suppresses reach on them."""

    if state.get("custom_rules"):
        # The author's rules ARE the style spec. Don't hand the model a second,
        # generic craft checklist to blend with them — that blend is exactly why
        # posts came out only half in-voice.
        style_layer = """STYLE — FOLLOW THE AUTHOR'S RULES ABOVE, LITERALLY:
The author's rules are your complete style specification. Voice, structure,
hooks, examples, length, tone, endings and hashtags all come from there — not
from any generic notion of a good LinkedIn post. Do not fall back on a default
LinkedIn voice, and do not add anything the rules don't ask for. When your
instinct and the rules differ, the rules win, every time. Before you finish,
re-read the author's rules and check the draft against them line by line."""
    else:
        style_layer = """CRAFT (defaults):
- Open with a hook in the first two lines; that is the "see more" cut-off.
- Short paragraphs with line breaks between them.
- Prefer a concrete technical example, a comparison, or real code over a story.
- End with a question or CTA that invites a genuine answer.
- Add 3-4 hashtags at the end, only where they aid discovery.
- Keep under 250 words.
- Write as a peer, not a teacher."""

    # These are the specific "an AI wrote this" tells the author flagged. They
    # reinforce the persona rather than compete with it, so they apply either
    # way — but they are framed as things to AVOID, not a rival style to adopt.
    voice_tells = """AVOID THESE AI TELLS — they are what gives away that a human didn't write this:
- Narrator/storytelling openers: "Picture this", "Let me tell you a story", "Imagine a world where". If you set up a scenario, use plain framings the author would type, e.g. "Suppose you're building..." or "Imagine two users clicking Pay at the same time...".
- Hedge endings that fit any topic: "use it judiciously", "find the balance", "it depends", "use it wisely". End on one specific, memorable line instead — e.g. "Complexity doesn't disappear, it just moves."
- Vague complexity claims. Name the actual mechanism (rebuilding aggregates, snapshotting, read-model lag, replaying events) instead of saying "it adds complexity".
- Essay words nobody says out loud: judiciously, leverage, delve, myriad, robust, seamless, "in the realm of", "it's worth noting", "a match made in heaven".
- Long, clause-packed sentences. Prefer short, declarative statements."""

    system_prompt = f"""You are a LinkedIn ghostwriter for a Senior Software Development Engineer
with 12+ years of experience.{rules_block}

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

{hard_constraints}

{style_layer}

{voice_tells}"""

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
        rules = state.get("custom_rules", "")
        # The reviewer is checked against the same rules the writer was given —
        # otherwise a rule-breaking draft can still pass the gate.
        rules_section = (
            f"\n\nThe author's own rules (a breach of these is an automatic fail):\n{rules}"
            if rules
            else ""
        )
        examples = state.get("similar_past_posts") or []
        examples_section = (
            "\n\nThe author's real posts, for voice comparison:\n"
            + "\n\n---\n\n".join(examples[:2])
            if examples
            else ""
        )
        try:
            feedback = await llm_service.call_structured(
                "You review LinkedIn drafts against the author's own rules and voice. "
                "Score and give actionable feedback.",
                f"""Draft:\n{state.get('draft_content', '')}\n\n"""
                f"""Style profile:\n{state.get('style_profile', 'None')}"""
                f"""{rules_section}{examples_section}\n\n"""
                """Return JSON: {"score": 0-100, "feedback": "2-3 sentences naming what to change", "passes": true/false, "rule_breaches": ["..."]}""",
                light=True,
            )
            llm_score = feedback.get("score", 75)
            updates["style_score"] = (style_score * 0.4) + (llm_score * 0.6)
            note = feedback.get("feedback", "")
            breaches = feedback.get("rule_breaches") or []
            if breaches:
                note = f"{note}\nRule breaches to fix: " + "; ".join(
                    str(b) for b in breaches[:5]
                )
            updates["quality_feedback"] = note

            if breaches or not feedback.get("passes", True):
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
