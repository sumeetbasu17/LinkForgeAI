"""
Turns an uploaded inspiration image into a reusable style preset.

You cannot train a model on a handful of reference images. What you can do is
look at one properly, once, and write down what makes it work — palette,
emphasis treatment, layout archetype, footer furniture. That description is
saved as a preset and reused forever, so the vision model is called only at
upload time and never during post generation.
"""

from __future__ import annotations

import json
import re

from services import image_templates
from services.llm import llm_service

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

SYSTEM_PROMPT = """You analyse reference images for a LinkedIn post-image generator.

The generator redraws cards from HTML templates, so your job is to describe the
VISUAL STYLE precisely enough to reproduce it — not to describe the subject.

Pick exactly one archetype:
- "social-card": avatar, name, @handle, then a short question or take. No company badge.
- "interview-card": like social-card but adds a series/company badge, a coloured
  title, highlighted phrases, a call to action, and a footer strip.
- "code-card": a code screenshot, usually with a window chrome and syntax colours.
- "diagram": boxes, arrows, or an architecture/flow drawing.

Report colours as hex. Read them off the image; do not guess round numbers."""

USER_PROMPT = """Analyse this reference image and return JSON with exactly these keys:

{
  "archetype": "social-card | interview-card | code-card | diagram",
  "name": "short human label for this style, 2-4 words",
  "background": "#hex of the dominant background",
  "background_gradient": "a CSS gradient if the background clearly is one, else empty string",
  "text_color": "#hex of the body text",
  "muted_color": "#hex of secondary text such as the handle",
  "accent_color": "#hex of the colour used for emphasis and highlights",
  "title_color": "#hex of the headline colour, or empty string if same as accent",
  "highlight_style": "color | box | underline",
  "code_theme": "dark | light",
  "font_scale": 1.0,
  "series_label": "small uppercase label above or below the name, else empty string",
  "footer_left": "left-hand footer text, else empty string",
  "footer_right": "right-hand footer text, else empty string",
  "notes": "one sentence on what makes this layout work"
}

Return only the JSON object."""


def _clean_hex(value, fallback: str) -> str:
    value = str(value or "").strip()
    if _HEX.match(value):
        return value
    return fallback


def _sanitize(raw: dict) -> dict:
    """Coerce the model's answer into a preset the templates can safely use."""
    archetype = str(raw.get("archetype", "")).strip().lower()
    if archetype not in image_templates.ARCHETYPES:
        archetype = "social-card"

    highlight = str(raw.get("highlight_style", "color")).strip().lower()
    if highlight not in ("color", "box", "underline"):
        highlight = "color"

    code_theme = str(raw.get("code_theme", "dark")).strip().lower()
    if code_theme not in ("dark", "light"):
        code_theme = "dark"

    try:
        font_scale = max(0.6, min(1.6, float(raw.get("font_scale", 1.0))))
    except (TypeError, ValueError):
        font_scale = 1.0

    gradient = str(raw.get("background_gradient", "") or "").strip()
    # Only allow plain CSS gradient functions — this string goes into a style
    # attribute, so nothing else should reach the page.
    if gradient and not re.fullmatch(r"(linear|radial)-gradient\([^;{}<>\"']*\)", gradient):
        gradient = ""

    defaults = image_templates.DEFAULT_STYLE
    return {
        "archetype": archetype,
        "name": str(raw.get("name", "") or "")[:60],
        "style": {
            "background": _clean_hex(raw.get("background"), defaults["background"]),
            "background_gradient": gradient,
            "text_color": _clean_hex(raw.get("text_color"), defaults["text_color"]),
            "muted_color": _clean_hex(raw.get("muted_color"), defaults["muted_color"]),
            "accent_color": _clean_hex(raw.get("accent_color"), defaults["accent_color"]),
            "title_color": _clean_hex(raw.get("title_color"), ""),
            "highlight_style": highlight,
            "code_theme": code_theme,
            "font_scale": font_scale,
            "series_label": str(raw.get("series_label", "") or "")[:60],
            "footer_left": str(raw.get("footer_left", "") or "")[:60],
            "footer_right": str(raw.get("footer_right", "") or "")[:40],
            "notes": str(raw.get("notes", "") or "")[:300],
        },
    }


class ImageStyleAnalyzer:
    """Extracts a style preset from one reference image."""

    async def analyze(self, image_path: str) -> dict:
        """Return {"archetype", "name", "style"} for an uploaded image.

        Falls back to a sane default preset if the vision model is unavailable,
        so an upload never fails outright.
        """
        data_uri = image_templates.data_uri(image_path)
        if not data_uri:
            raise ValueError("Could not read the uploaded image")

        try:
            raw = await llm_service.call_vision(SYSTEM_PROMPT, USER_PROMPT, data_uri)
        except Exception as exc:
            return {
                "archetype": "social-card",
                "name": "Imported (not analysed)",
                "style": dict(image_templates.DEFAULT_STYLE),
                "warning": f"Style analysis unavailable: {str(exc)[:200]}",
            }

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]

        # Models occasionally wrap the object in prose; take the outermost braces.
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "archetype": "social-card",
                "name": "Imported (unreadable analysis)",
                "style": dict(image_templates.DEFAULT_STYLE),
                "warning": "The vision model did not return valid JSON.",
            }

        if not isinstance(parsed, dict):
            parsed = {}
        return _sanitize(parsed)


image_style_analyzer = ImageStyleAnalyzer()
