"""Tests for when a post earns an image.

The rule: default NO, with one carve-out — a system-design / low-level-design
post that names components and how data moves between them gets a diagram even
when the writing is reflective. That case was being refused because the decision
model judged the tone rather than the content.

Run with:  python backend/tests/test_visual_agent.py
      or:  pytest backend/tests/test_visual_agent.py
"""

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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

from services import visual_agent as va  # noqa: E402
from services.llm import llm_service  # noqa: E402

# The real post from the app that came back with no image.
CQRS_POST = """Ever tried to balance the needs of a high-concurrency system with
the elegance of Event Sourcing and CQRS?

On paper, Event Sourcing is a dream. Every change is stored as an event, giving
you a rich history of everything that's happened in your system.

But here's the catch: the read side of things isn't always that straightforward.

Imagine you've built this detailed event log. Now you want to generate reports or
update dashboards. Suddenly your read models are lagging behind your write
models. This is what we call eventual consistency.

And then there's the data size. With every change stored as an event, your data
can grow faster than you expect."""

CULTURE_POST = """Your manager sets the entire tone of your team.

Their personality, their vibes, their values, it all trickles down. The best
managers I've seen protect their people's focus and take the blame upward.

Who was the manager that changed how you work?"""


def _model_says(needs, archetype="social-card", reason="because"):
    async def _fake(system_prompt, user_prompt, **kwargs):
        return {"needs_image": needs, "archetype": archetype, "reason": reason}

    llm_service.call_structured = _fake


def test_reflective_design_post_still_gets_a_diagram():
    """The model calls it a reflection; the content is a drawable flow."""
    _model_says(False, "", "This is a reflective post about trade-offs")
    decision = asyncio.run(
        va.visual_agent.decide(CQRS_POST, category="system-design", format="reflection")
    )
    assert decision["needs_image"] is True, decision
    assert decision["archetype"] == "diagram", decision


def test_a_question_card_for_a_design_post_becomes_a_diagram():
    _model_says(True, "social-card")
    decision = asyncio.run(va.visual_agent.decide(CQRS_POST, category="system-design"))
    assert decision["archetype"] == "diagram", decision


def test_culture_post_gets_nothing_even_in_a_design_category():
    _model_says(False, "", "Career advice — no artifact")
    decision = asyncio.run(
        va.visual_agent.decide(CULTURE_POST, category="system-design")
    )
    assert decision["needs_image"] is False, decision


def test_career_post_in_its_own_category_gets_nothing():
    _model_says(True, "social-card")
    decision = asyncio.run(
        va.visual_agent.decide(CULTURE_POST, category="career-growth")
    )
    assert decision["needs_image"] is False, decision


def test_code_card_still_needs_actual_code():
    _model_says(True, "code-card")
    decision = asyncio.run(
        va.visual_agent.decide(CULTURE_POST, category="career-growth")
    )
    assert decision["needs_image"] is False
    assert "No code" in decision["reason"]


def test_design_carve_out_needs_several_named_parts():
    """One buzzword is not a system. Three or more named parts is."""
    thin = "Caching is underrated. Most teams reach for it too late in my view."
    assert va.visual_agent._design_diagram_case(thin, "system-design") is False
    assert va.visual_agent._design_diagram_case(CQRS_POST, "system-design") is True


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
