"""
Decides whether a post should carry an image, picks the archetype, and writes
the content that goes inside it.

The model never draws anything. It answers two questions — "is there something
here worth showing?" and "what words go in the card?" — and the templates do
the drawing. That split is what keeps handles, code and diagram labels correct.
"""

from __future__ import annotations

import json
import re

from services import image_templates
from services.llm import llm_service

# Archetypes this agent is allowed to choose.
SUPPORTED = ["social-card", "interview-card", "code-card", "diagram"]

DECIDE_SYSTEM = """You decide whether a LinkedIn post is better with an image.

Default to NO. Most posts do not need one. A weak image is worse than no image,
because it makes a thoughtful post look like filler.

Say YES only when the post contains a concrete artifact a reader could not
simply restate in words:
- a technical puzzle with a right answer the post then explains (social-card or
  interview-card)
- actual code, config, or a query the post is about (code-card)
- a system, flow, or pipeline with named components and a direction of travel
  (diagram)

Say NO for:
- opinions, reflections, and personal stories, however good
- leadership, culture, mindset, motivation, burnout, or career advice
- posts whose only "question" is an engagement prompt aimed at the reader

ONE EXCEPTION, and it matters: a post about system design, architecture, or
object-oriented / low-level design that names components and how data moves
between them earns a diagram even when the tone is reflective. "Event sourcing
writes to an event store, projections build read models, the read side lags"
is a drawable flow, and a reader scrolling past a wall of text will stop for
the picture. Judge the content, not the mood of the writing.

THE TEST THAT MATTERS — is the question technical or conversational?

  "What happens to a payment that's halfway done when the service crashes?"
      -> technical. It has a correct answer the post supplies. YES.

  "Who was the manager that built a great culture around you?"
      -> conversational. It invites the reader to share, and the image would
         only repeat the post's opinion back. NO.

A bulleted list is not a diagram. A rhetorical question is not an interview
question. If you are weighing it up, the answer is NO.

Choose exactly one archetype from: social-card, interview-card, code-card, diagram."""

DECIDE_USER = """Post:
---
{post}
---
Category: {category}
Format: {format}

Ask yourself in order:
1. Is there a named system, flow, or class structure with components and a
   direction of travel? -> diagram (this outranks the others for design posts)
2. Is there code, config, or a query in this post? -> code-card
3. Does it pose a technical problem with a correct answer? -> social/interview-card
4. Otherwise -> needs_image is false.

Return JSON:
{{"needs_image": true or false, "archetype": "...", "reason": "one short sentence"}}"""

# Cheap signals used to second-guess the model when it asks for a card that the
# post cannot actually fill.
_CODE_SIGNAL = re.compile(
    r"```|\b(class|def |function |public |private |import |SELECT |@\w+\()|[{};]\s*$",
    re.MULTILINE,
)
_FLOW_SIGNAL = re.compile(
    r"->|-->|→|\b(pipeline|architecture|flow|request|queue|broker|consumer|producer|"
    r"service|gateway|cache|database|endpoint|topic|partition|replica|load balancer|"
    # Event-driven and CQRS vocabulary. A post can describe a whole drawable
    # system in these words without using any of the ones above.
    r"event sourcing|event store|event log|projection|read model|write model|"
    r"command|aggregate|saga|outbox|idempoten\w*|cqrs|stream|snapshot|"
    # Object and low-level design.
    r"class|interface|abstract|inheritance|composition|state machine|"
    r"thread|lock|worker|shard|index|transaction|retry|throttl\w*)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(r"\?")

# Categories where a diagram is the point, not decoration. A reflective post
# about CQRS still describes a system somebody can draw.
DESIGN_CATEGORIES = {"system-design", "tech-concepts", "clean-code"}


CONTENT_SYSTEM = """You write the text that goes inside a LinkedIn post image.

Rules:
- The image poses or frames; the post itself answers. Never give away the answer.
- Keep it short. A card is read in two seconds, not two minutes.
- Mark emphasis with **bold** and ==highlight== (highlight is the accent colour).
- Never invent statistics, company names, or job titles.
- Write in the author's voice, matching the post you are given."""

CONTENT_PROMPTS = {
    "social-card": """Write a social card for this post.

Return JSON:
{{"body": "2-4 very short paragraphs, separated by blank lines. Usually a setup line then a question."}}

Post:
---
{post}
---""",
    "interview-card": """Write an interview-question card for this post.

Return JSON:
{{
  "title": "3-6 word headline",
  "body": "2-3 short paragraphs setting up the problem, using **bold** and ==highlight==",
  "cta": "one line inviting an answer, e.g. Explain your approach in comments below?",
  "series_name": "short topic name, 1-3 words",
  "series_label": "uppercase label, 2-4 words",
  "footer_left": "uppercase series name",
  "footer_right": "ANSWER BELOW"
}}

Post:
---
{post}
---""",
    "code-card": """Write a code card for this post.

Use code that actually appears in or is clearly implied by the post. Keep it
under 20 lines and make sure it compiles as written.

Return JSON:
{{
  "title": "short headline, or empty string",
  "language": "java | python | javascript | sql | yaml | bash",
  "code": "the snippet",
  "caption": "one short line under the code, or empty string"
}}

For a before/after comparison, return instead:
{{"title": "...", "language": "...", "before_label": "before", "before_code": "...",
  "after_label": "after", "after_code": "...", "caption": "..."}}

Post:
---
{post}
---""",
    "diagram": """Write a diagram for this post as Mermaid source.

Rules:
- Use `flowchart LR` or `flowchart TD`.
- At most 8 nodes. Short labels, 1-3 words.
- Plain ASCII in node labels — no emoji, no quotes, no parentheses inside text.
- The diagram must be valid Mermaid; it is rendered as-is.

Return JSON:
{{"title": "short headline", "mermaid": "flowchart LR\\n  A[Client] --> B[API]",
  "caption": "one short line, or empty string"}}

Post:
---
{post}
---""",
}


def _parse_json(raw) -> dict:
    """Pull a JSON object out of a model response."""
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def infer_archetype(payload: dict) -> str:
    """Recover the archetype a payload was written for from its shape.

    A payload and its archetype are written together, but they can be sent to
    the renderer separately (the Editor forwards a saved payload while leaving
    the archetype blank). Defaulting a blank archetype to "social-card" then
    renders, say, a diagram payload through the wrong template — the mermaid is
    dropped and a bare title card comes out. Reading the archetype back off the
    payload keys keeps the two in step.
    """
    if not isinstance(payload, dict) or not payload:
        return ""
    if payload.get("mermaid"):
        return "diagram"
    if payload.get("code") or payload.get("before_code") or payload.get("after_code"):
        return "code-card"
    # interview cards carry a call-to-action / series framing; social cards are
    # just a body block.
    if payload.get("cta") or payload.get("series_label") or payload.get("footer_right"):
        return "interview-card"
    if payload.get("body") or payload.get("text"):
        return "social-card"
    return ""


def sanitize_mermaid(source: str) -> str:
    """Make LLM-written Mermaid safe to render.

    Mermaid fails hard on a syntax error and would otherwise produce a card
    with an error message where the diagram should be.
    """
    source = (source or "").strip()
    if not source:
        return "flowchart LR\n  A[Start] --> B[End]"

    # Strip a fenced block if the model wrapped it.
    source = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", source).strip()

    lines = []
    for line in source.split("\n"):
        # Quotes and semicolons inside labels are the usual cause of failure.
        line = line.replace('"', "").replace(";", "")
        lines.append(line.rstrip())

    cleaned = "\n".join(l for l in lines if l.strip())
    if not re.match(r"^\s*(flowchart|graph|sequenceDiagram|erDiagram|classDiagram)", cleaned):
        cleaned = "flowchart LR\n" + cleaned
    return cleaned


class VisualAgent:
    """Chooses whether and what to draw for a post."""

    async def decide(self, post: str, category: str = "", format: str = "") -> dict:
        """Return {"needs_image": bool, "archetype": str, "reason": str}."""
        if not post or len(post.strip()) < 40:
            return {"needs_image": False, "archetype": "", "reason": "Post too short"}

        try:
            raw = await llm_service.call_structured(
                DECIDE_SYSTEM,
                DECIDE_USER.format(
                    post=post[:3000], category=category or "unspecified",
                    format=format or "unspecified",
                ),
                light=True,
            )
        except Exception as exc:
            return {
                "needs_image": False,
                "archetype": "",
                "reason": f"Decision unavailable: {str(exc)[:120]}",
            }

        data = _parse_json(raw)
        archetype = str(data.get("archetype", "")).strip().lower()
        if archetype not in SUPPORTED:
            archetype = "social-card"

        needs = bool(data.get("needs_image"))
        reason = str(data.get("reason", ""))[:200]

        if needs:
            # A drawable design post is better as a diagram than as a question
            # card, whichever way the model leaned.
            if archetype in ("social-card", "interview-card") and self._design_diagram_case(
                post, category
            ):
                archetype = "diagram"
                reason = "Design post describing a flow — drawn instead of framed"
            veto = self._veto(post, archetype, category)
            if veto:
                return {"needs_image": False, "archetype": "", "reason": veto}
        elif self._design_diagram_case(post, category):
            # The model leans on tone and calls anything thoughtful a
            # "reflection". A design post that names components and their flow
            # is exactly where a diagram earns its place, so overrule the no.
            return {
                "needs_image": True,
                "archetype": "diagram",
                "reason": "Design post describing a flow — a diagram carries this",
            }

        return {"needs_image": needs, "archetype": archetype, "reason": reason}

    def _design_diagram_case(self, post: str, category: str) -> bool:
        """True for a design-category post with enough named parts to draw."""
        if (category or "").strip().lower() not in DESIGN_CATEGORIES:
            return False
        hits = {m.group(0).lower() for m in _FLOW_SIGNAL.finditer(post)}
        return len(hits) >= 3

    def _veto(self, post: str, archetype: str, category: str = "") -> str:
        """Second-guess a yes when the post can't actually fill the card.

        The model is the primary judge, but it tends to say yes to anything
        ending in a question mark. These checks look for the raw material the
        archetype needs and overrule it when there is none. Returns a reason
        to skip, or "" to let the decision stand.
        """
        if archetype == "code-card" and not _CODE_SIGNAL.search(post):
            return "No code in the post to put in a code card"

        if archetype == "diagram" and not _FLOW_SIGNAL.search(post):
            return "No system or flow in the post to draw"

        if archetype in ("social-card", "interview-card"):
            # These cards exist to pose a problem. If the post asks nothing, or
            # only asks the reader to share an experience, there is nothing to
            # frame — the image would just restate the opinion.
            if not _QUESTION.search(post):
                return "Post poses no question to frame"
            if not (_CODE_SIGNAL.search(post) or _FLOW_SIGNAL.search(post)):
                return "Reflection or opinion — no technical problem to pose"

        return ""

    async def write_payload(self, post: str, archetype: str) -> dict:
        """Write the content that fills the chosen template."""
        if archetype not in SUPPORTED:
            archetype = "social-card"

        try:
            raw = await llm_service.call_structured(
                CONTENT_SYSTEM,
                CONTENT_PROMPTS[archetype].format(post=post[:4000]),
                light=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not write image content: {str(exc)[:200]}") from exc

        payload = _parse_json(raw)
        if not payload:
            raise RuntimeError("The model did not return usable image content")

        if archetype == "diagram":
            payload["mermaid"] = sanitize_mermaid(payload.get("mermaid", ""))
        if archetype == "social-card" and not payload.get("body"):
            payload["body"] = payload.get("text", "") or post[:280]
        return payload

    async def plan(self, post: str, category: str = "", format: str = "") -> dict:
        """Decide and, if worthwhile, write the content in one step."""
        decision = await self.decide(post, category, format)
        if not decision["needs_image"]:
            return {**decision, "payload": {}}
        payload = await self.write_payload(post, decision["archetype"])
        return {**decision, "payload": payload}


visual_agent = VisualAgent()
