"""Tests that the writer prompt actually carries the user's rules and examples.

These were the three quiet failures: custom rules sat at the bottom of the user
message where the generic defaults outranked them, the style profile was empty
unless "Analyze my style" had been clicked, and retrieval ran on the raw
category id before a topic existed.

The vector store and the HTTP client are stubbed, so this runs with no
embedding backend, no API key and no network.

Run with:  python backend/tests/test_prompt_assembly.py
      or:  pytest backend/tests/test_prompt_assembly.py
"""

import asyncio
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Stub optional third-party imports ────────────────────────────
for _name in ("httpx", "dotenv"):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            _mod = types.ModuleType(_name)
            if _name == "httpx":
                _mod.AsyncClient = object
            else:
                _mod.load_dotenv = lambda *a, **k: None
            sys.modules[_name] = _mod

# ─── Stub the vector store so no embedding backend is needed ──────
# The stub mirrors the real library's shape: a category-filtered search only
# returns posts filed under that category, and thin shelves return less than
# asked for, which is what the top-up path exists to handle.
_LIBRARY = {
    ("own", "system-design"): 2,
    ("own", "genai-tools"): 1,
    ("inspiration", "system-design"): 3,
    ("inspiration", "genai-tools"): 1,
}


def _fake_search(content, user_id, post_type=None, category=None, limit=3):
    _fake_vector_store.calls.append(
        {"query": content, "post_type": post_type, "category": category}
    )
    if category is None:  # unfiltered: the whole library is in range
        available = limit
        tag = "any-category"
    else:
        available = _LIBRARY.get((post_type, category), 0)
        tag = category
    return [
        {"content": f"[{post_type} {tag} #{i} for '{content[:24]}']", "category": tag}
        for i in range(1, min(limit, available) + 1)
    ]


_fake_vector_store = types.SimpleNamespace(
    calls=[],
    find_similar_posts=_fake_search,
    compute_style_similarity=lambda draft, user_id: 42.0,
    add_post=lambda *a, **k: "id",
)
sys.modules["db.vector_store"] = types.ModuleType("db.vector_store")
sys.modules["db.vector_store"].vector_store = _fake_vector_store

import db.database as db_module  # noqa: E402

db_module.database = db_module.Database(
    os.path.join(tempfile.mkdtemp(), "prompts.db")
)

from agents import nodes  # noqa: E402
from services.llm import llm_service  # noqa: E402

nodes.database = db_module.database

USER = "default"
RULES = "- Never use the word synergy\n- Always open with a question\n- No hashtags at all"

captured: dict = {}


async def _fake_heavy(system_prompt, user_prompt, **kwargs):
    captured["system"] = system_prompt
    captured["user"] = user_prompt
    return "Drafted post body."


async def _fake_structured(system_prompt, user_prompt, **kwargs):
    captured.setdefault("structured", []).append((system_prompt, user_prompt))
    return {"title": "A title", "score": 80, "feedback": "fine", "passes": True}


llm_service.call_heavy = _fake_heavy
llm_service.call_structured = _fake_structured


def _seed_own_posts(n=3):
    for i in range(n):
        db_module.database.add_style_post(
            post_id=f"style_own_{i}",
            content=(
                f"Own post {i}.\n\nProduction taught me to plan for failure.\n\n"
                "Short lines. Plain words. A question at the end?"
            ),
            post_type="own",
            user_id=USER,
        )


def test_custom_rules_land_in_the_system_prompt():
    db_module.database.update_preferences(USER, custom_rules=RULES)
    state = asyncio.run(nodes.load_style_context({"user_id": USER, "category": "clean-code"}))
    state.update({"selected_topic": "Immutability in Java", "format": "story"})
    asyncio.run(nodes.draft_post(state))

    assert "Never use the word synergy" in captured["system"], "rules missing from system prompt"
    assert "HIGHEST PRIORITY" in captured["system"]
    # And the defaults must yield to them, in writing. When custom rules exist,
    # the generic craft checklist is dropped and the style layer states outright
    # that the author's rules are the spec and win over instinct.
    assert "the rules win, every time" in captured["system"]
    # The competing generic craft checklist must NOT be present alongside the
    # author's rules — that blend is what diluted the voice.
    assert "CRAFT (defaults)" not in captured["system"]


def test_style_profile_is_derived_when_analysis_never_ran():
    db_module.database.update_preferences(USER, style_profile={})
    _seed_own_posts()
    updates = asyncio.run(
        nodes.load_style_context({"user_id": USER, "category": "clean-code"})
    )
    assert updates["style_profile"], "expected a fallback profile from stored posts"
    assert "Average post length" in updates["style_profile"]
    # It is cached so the Style tab is no longer blank either.
    saved = db_module.database.get_preferences(USER)["style_profile"]
    assert saved.get("avg_word_count", 0) > 0


def test_own_and_inspiration_posts_both_reach_the_prompt():
    state = asyncio.run(nodes.load_style_context({"user_id": USER, "category": "system-design"}))
    assert state["similar_past_posts"], "no own posts retrieved"
    assert state["inspiration_structures"], "no inspiration posts retrieved"

    state.update({"selected_topic": "Eventual consistency", "format": "listicle"})
    asyncio.run(nodes.draft_post(state))
    body = captured["user"]
    assert "own system-design #1" in body
    assert "inspiration system-design #1" in body
    assert "THIS is the voice to reproduce" in body
    # Same subject is allowed; reusing their words is not.
    assert "ANGLE and the SHAPE" in body
    assert "reusing their sentences" in body


def test_retrieval_prefers_the_posts_own_category():
    _fake_vector_store.calls.clear()
    asyncio.run(nodes.load_style_context({"user_id": USER, "category": "system-design"}))
    first = _fake_vector_store.calls[0]
    assert first["category"] == "system-design", "category filter not applied first"


def test_thin_category_is_topped_up_from_the_whole_library():
    """genai-tools holds one own post — the rest must still come back."""
    _fake_vector_store.calls.clear()
    state = asyncio.run(
        nodes.load_style_context({"user_id": USER, "category": "genai-tools"})
    )
    categories = [c["category"] for c in _fake_vector_store.calls]
    assert "genai-tools" in categories and None in categories, "no top-up search"
    assert len(state["similar_past_posts"]) == 3, state["similar_past_posts"]
    assert any("genai-tools" in p for p in state["similar_past_posts"])
    assert any("any-category" in p for p in state["similar_past_posts"])


def test_inspiration_posts_seed_topic_selection():
    captured["structured"] = []
    asyncio.run(
        nodes.select_topic(
            {
                "user_id": USER,
                "category": "system-design",
                "format": "listicle",
                "inspiration_structures": ["Idempotency keys are how you survive retries."],
            }
        )
    )
    topic_prompt = "\n".join(u for _s, u in captured["structured"])
    assert "Idempotency keys are how you survive retries." in topic_prompt
    assert "Inspiration posts saved under this category" in topic_prompt


def test_retrieval_uses_category_words_not_the_raw_id():
    _fake_vector_store.calls.clear()
    asyncio.run(nodes.load_style_context({"user_id": USER, "category": "system-design"}))
    queries = [c["query"] for c in _fake_vector_store.calls]
    assert queries, "no retrieval happened"
    assert all("system-design" != q for q in queries), "queried the raw id"
    assert any("System Design" in q or "system" in q.lower() for q in queries)


def test_topic_refresh_requeries_with_the_chosen_topic():
    _fake_vector_store.calls.clear()
    updates = asyncio.run(
        nodes.refresh_style_context(
            {
                "user_id": USER,
                "category": "system-design",
                "selected_topic": "Idempotent consumers in Kafka",
            }
        )
    )
    queries = [c["query"] for c in _fake_vector_store.calls]
    assert any("Idempotent consumers in Kafka" in q for q in queries)
    assert updates["similar_past_posts"] and updates["inspiration_structures"]


def test_quality_check_reviews_against_the_rules():
    captured["structured"] = []
    asyncio.run(
        nodes.quality_check(
            {
                "user_id": USER,
                "draft_content": "A draft that uses synergy everywhere. #hashtag",
                "custom_rules": RULES,
                "similar_past_posts": ["An earlier real post of mine."],
                "revision_count": 0,
                "max_revisions": 2,
            }
        )
    )
    reviewer_prompt = "\n".join(u for _s, u in captured["structured"])
    assert "Never use the word synergy" in reviewer_prompt
    assert "rule_breaches" in reviewer_prompt


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
