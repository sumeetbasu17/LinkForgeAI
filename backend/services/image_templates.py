"""
HTML templates for generated post images.

The images are rendered from HTML rather than produced by an image model.
Every archetype here is text in a layout — handles, code, and diagram labels
have to be exactly right, which is the one thing diffusion models are worst
at. Templates give pixel-accurate text, the real avatar, and the same output
every run at no per-image cost.

Each template takes three inputs:
  payload  — the content the LLM wrote for this specific post
  style    — a preset, usually extracted from an uploaded inspiration image
  identity — display name, headline, avatar, badge, and the chosen handle
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

ARCHETYPES = ["social-card", "interview-card", "code-card", "diagram"]

# Rendered width in CSS pixels. Squares and portraits both read well in the
# LinkedIn feed; the renderer crops to the card's real height.
CARD_WIDTH = 1080

# Fonts installed in the container (see Dockerfile). Emoji need their own
# family or they render as empty boxes.
FONT_STACK = (
    "'Inter', 'Noto Sans', 'DejaVu Sans', -apple-system, BlinkMacSystemFont, "
    "'Segoe UI', Roboto, sans-serif, 'Noto Color Emoji'"
)
MONO_STACK = (
    "'JetBrains Mono', 'Noto Sans Mono', 'DejaVu Sans Mono', "
    "ui-monospace, Menlo, Consolas, monospace, 'Noto Color Emoji'"
)

DEFAULT_STYLE: dict = {
    "background": "#000000",
    "background_gradient": "",
    "text_color": "#FFFFFF",
    "muted_color": "#8B8B90",
    "accent_color": "#E5484D",
    "title_color": "",
    "highlight_style": "color",  # color | box | underline
    "font_scale": 1.0,
    "padding": 64,
    "divider_color": "rgba(255,255,255,0.14)",
    "code_theme": "dark",
    "series_name": "",
    "series_label": "",
    "footer_left": "",
    "footer_right": "",
}


# ─── Small helpers ────────────────────────────────────────────────


def merge_style(style: dict | None) -> dict:
    merged = dict(DEFAULT_STYLE)
    for key, value in (style or {}).items():
        if value is not None and value != "":
            merged[key] = value
    try:
        merged["font_scale"] = max(0.6, min(1.6, float(merged["font_scale"])))
    except (TypeError, ValueError):
        merged["font_scale"] = 1.0
    return merged


def data_uri(path: str) -> str:
    """Inline a local image so the renderer needs no file access."""
    if not path:
        return ""
    file = Path(path)
    if not file.is_file():
        return ""
    mime = mimetypes.guess_type(file.name)[0] or "image/png"
    try:
        encoded = base64.b64encode(file.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime};base64,{encoded}"


def format_inline(text: str, style: dict) -> str:
    """Convert the lightweight markers the LLM writes into styled HTML.

    **bold**      strong emphasis
    ==highlight== the accent treatment seen in the inspiration cards
    `code`        inline monospace
    """
    escaped = html.escape(text or "")

    accent = style["accent_color"]
    mode = style.get("highlight_style", "color")
    if mode == "box":
        mark = (
            f'<span style="background:{accent};color:#fff;padding:2px 10px;'
            'border-radius:6px;font-weight:700;">\\1</span>'
        )
    elif mode == "underline":
        mark = (
            f'<span style="color:{accent};font-weight:700;'
            f'border-bottom:4px solid {accent};">\\1</span>'
        )
    else:
        mark = f'<span style="color:{accent};font-weight:700;">\\1</span>'

    escaped = re.sub(r"==(.+?)==", mark, escaped, flags=re.DOTALL)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
    escaped = re.sub(
        r"`(.+?)`",
        r'<code style="font-family:' + MONO_STACK + r';font-size:0.92em;">\1</code>',
        escaped,
    )
    return escaped.replace("\n", "<br>")


def paragraphs(text: str, style: dict, gap: int = 28) -> str:
    """Render body copy, preserving the blank-line rhythm of a LinkedIn post."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return "".join(
        f'<p style="margin:0 0 {gap}px 0;">{format_inline(b, style)}</p>'
        for b in blocks
    )


def _verified_badge(color: str, size: int = 34) -> str:
    """Inline SVG check badge, so no external asset is needed."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'style="flex:0 0 auto;vertical-align:middle;">'
        f'<path fill="{html.escape(color)}" d="M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.9-.81-3.91'
        "s-2.52-1.27-3.91-.81C14.67 2.63 13.43 1.75 12 1.75s-2.67.88-3.34 2.19"
        "c-1.39-.46-2.9-.2-3.91.81s-1.27 2.52-.81 3.91c-1.31.67-2.19 1.91-2.19 3.34"
        "s.88 2.67 2.19 3.34c-.46 1.39-.2 2.9.81 3.91s2.52 1.27 3.91.81"
        "c.67 1.31 1.91 2.19 3.34 2.19s2.67-.88 3.34-2.19c1.39.46 2.9.2 3.91-.81"
        's1.27-2.52.81-3.91c1.31-.67 2.19-1.91 2.19-3.34z"/>'
        '<path fill="#fff" d="M10.6 16.2 6.4 12l1.4-1.4 2.8 2.8 5.6-5.6L17.6 9z"/>'
        "</svg>"
    )


def _avatar(identity: dict, size: int) -> str:
    uri = data_uri(identity.get("avatar_path", ""))
    common = (
        f"width:{size}px;height:{size}px;border-radius:50%;"
        "object-fit:cover;flex:0 0 auto;"
    )
    if uri:
        return f'<img src="{uri}" style="{common}">'
    initials = "".join(w[0] for w in (identity.get("display_name") or "?").split()[:2])
    return (
        f'<div style="{common}background:#2A2A2E;display:flex;align-items:center;'
        f'justify-content:center;font-size:{int(size * 0.4)}px;font-weight:700;'
        f'color:#fff;">{html.escape(initials.upper())}</div>'
    )


def _identity_header(identity: dict, handle: str, style: dict, scale: float,
                     avatar_size: int = 96, name_size: int = 42) -> str:
    """The name / badge / handle row every card variant opens with."""
    name = html.escape(identity.get("display_name") or "")
    headline = html.escape(identity.get("headline") or "")
    badge = (
        _verified_badge(identity.get("verified_color") or "#1D9BF0", int(name_size * 0.8))
        if identity.get("verified")
        else ""
    )
    handle_html = (
        f'<div style="color:{style["muted_color"]};font-size:{int(name_size * 0.85 * scale)}px;'
        f'line-height:1.25;">{html.escape(handle)}</div>'
        if handle
        else ""
    )
    headline_html = (
        f'<div style="color:{style["muted_color"]};font-size:{int(name_size * 0.62 * scale)}px;'
        f'line-height:1.3;margin-top:4px;">{headline}</div>'
        if headline
        else ""
    )
    return f"""
    <div style="display:flex;align-items:center;gap:{int(24 * scale)}px;">
      {_avatar(identity, int(avatar_size * scale))}
      <div style="min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="font-weight:800;font-size:{int(name_size * scale)}px;
                       line-height:1.2;">{name}</span>{badge}
        </div>
        {handle_html}
        {headline_html}
      </div>
    </div>"""


def _shell(body: str, style: dict, extra_head: str = "") -> str:
    """Wrap a card body in the page chrome the renderer screenshots."""
    background = style["background_gradient"] or style["background"]
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">{extra_head}
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; padding:0; background:transparent; }}
  #card {{
    width:{CARD_WIDTH}px;
    background:{background};
    color:{style["text_color"]};
    font-family:{FONT_STACK};
    padding:{style["padding"]}px;
    -webkit-font-smoothing:antialiased;
  }}
  b, strong {{ font-weight:800; }}
</style></head>
<body><div id="card">{body}</div></body></html>"""


# ─── Archetype 1: social card ─────────────────────────────────────


def render_social_card(payload: dict, style: dict, identity: dict, handle: str) -> str:
    """A post-style card: avatar, name, handle, then a question or short take.

    This is the "question in the image, answer in the post" format.
    """
    scale = style["font_scale"]
    body = payload.get("body", "") or payload.get("text", "")
    title = payload.get("title", "")

    title_html = ""
    if title:
        color = style["title_color"] or style["accent_color"]
        title_html = (
            f'<div style="font-size:{int(46 * scale)}px;font-weight:800;color:{color};'
            f'margin:0 0 {int(28 * scale)}px 0;line-height:1.25;">'
            f"{format_inline(title, style)}</div>"
        )

    return _shell(
        f"""
      {_identity_header(identity, handle, style, scale)}
      <div style="margin-top:{int(52 * scale)}px;font-size:{int(42 * scale)}px;
                  line-height:1.45;font-weight:500;">
        {title_html}
        {paragraphs(body, style, gap=int(34 * scale))}
      </div>""",
        style,
    )


# ─── Archetype 2: interview card ──────────────────────────────────


def render_interview_card(payload: dict, style: dict, identity: dict, handle: str) -> str:
    """The richer variant: series badge, coloured title, highlights, CTA footer."""
    scale = style["font_scale"]
    accent = style["accent_color"]
    muted = style["muted_color"]

    series_name = payload.get("series_name") or style.get("series_name") or ""
    series_label = payload.get("series_label") or style.get("series_label") or ""
    series_html = ""
    if series_name or series_label:
        series_html = f"""
        <div style="display:flex;align-items:center;gap:{int(20 * scale)}px;
                    margin-top:{int(38 * scale)}px;">
          <div style="width:{int(64 * scale)}px;height:{int(64 * scale)}px;border-radius:10px;
                      background:{accent};display:flex;align-items:center;justify-content:center;
                      font-weight:800;font-size:{int(30 * scale)}px;color:#fff;flex:0 0 auto;">
            {html.escape((series_name or "?")[:1].upper())}
          </div>
          <div>
            <div style="font-weight:800;font-size:{int(30 * scale)}px;line-height:1.2;">
              {html.escape(series_name)}</div>
            <div style="color:{muted};font-size:{int(21 * scale)}px;letter-spacing:2.5px;
                        text-transform:uppercase;margin-top:3px;">
              {html.escape(series_label)}</div>
          </div>
        </div>"""

    title = payload.get("title", "")
    title_html = ""
    if title:
        color = style["title_color"] or accent
        title_html = (
            f'<div style="font-size:{int(48 * scale)}px;font-weight:800;color:{color};'
            f'margin:{int(44 * scale)}px 0 {int(30 * scale)}px 0;line-height:1.25;">'
            f"{format_inline(title, style)}</div>"
        )

    cta = payload.get("cta", "")
    cta_html = (
        f'<div style="margin-top:{int(64 * scale)}px;font-size:{int(34 * scale)}px;'
        f'line-height:1.4;">{format_inline(cta, style)}</div>'
        if cta
        else ""
    )

    footer_left = payload.get("footer_left") or style.get("footer_left") or ""
    footer_right = payload.get("footer_right") or style.get("footer_right") or ""
    footer_html = ""
    if footer_left or footer_right:
        arrow = (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:{int(40 * scale)}px;height:{int(40 * scale)}px;border-radius:50%;'
            f'background:{accent}33;color:{accent};font-size:{int(22 * scale)}px;'
            'margin-left:12px;">&#8595;</span>'
            if footer_right
            else ""
        )
        footer_html = f"""
        <div style="margin-top:{int(40 * scale)}px;padding-top:{int(28 * scale)}px;
                    border-top:1px solid {style["divider_color"]};
                    display:flex;align-items:center;justify-content:space-between;">
          <div style="display:flex;align-items:center;gap:12px;color:{style["text_color"]};
                      font-size:{int(22 * scale)}px;letter-spacing:3px;text-transform:uppercase;
                      font-weight:700;">
            <span style="color:{accent};font-size:{int(26 * scale)}px;">&bull;</span>
            {html.escape(footer_left)}
          </div>
          <div style="display:flex;align-items:center;color:{accent};font-size:{int(22 * scale)}px;
                      letter-spacing:2.5px;text-transform:uppercase;font-weight:700;">
            {html.escape(footer_right)}{arrow}
          </div>
        </div>"""

    return _shell(
        f"""
      {_identity_header(identity, handle, style, scale, avatar_size=76, name_size=34)}
      {series_html}
      {title_html}
      <div style="font-size:{int(36 * scale)}px;line-height:1.5;font-weight:500;">
        {paragraphs(payload.get("body", ""), style, gap=int(30 * scale))}
      </div>
      {cta_html}
      {footer_html}""",
        style,
    )


# ─── Archetype 3: code card ───────────────────────────────────────

# Token palette matched to the inspiration screenshots.
CODE_THEMES = {
    "dark": {
        "bg": "#282C34",
        "chrome": "#21252B",
        "page": "#1B1D23",
        "text": "#ABB2BF",
        "keyword": "#C678DD",
        "type": "#E5C07B",
        "name": "#61AFEF",
        "string": "#98C379",
        "number": "#D19A66",
        "comment": "#5C6370",
        "decorator": "#7F848E",
        "operator": "#E06C75",
    },
    "light": {
        "bg": "#FFFFFF",
        "chrome": "#F1F3F5",
        "page": "#E9ECEF",
        "text": "#24292E",
        "keyword": "#D73A49",
        "type": "#6F42C1",
        "name": "#005CC5",
        "string": "#032F62",
        "number": "#005CC5",
        "comment": "#6A737D",
        "decorator": "#6F42C1",
        "operator": "#D73A49",
    },
}


def highlight_code(code: str, language: str, theme: dict) -> str:
    """Syntax-highlight with Pygments, falling back to plain text."""
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_by_name, guess_lexer
        from pygments.token import Token

        try:
            lexer = get_lexer_by_name(language or "text")
        except Exception:
            try:
                lexer = guess_lexer(code)
            except Exception:
                return html.escape(code)

        mapping = [
            (Token.Comment, "comment"),
            (Token.Keyword, "keyword"),
            (Token.Name.Decorator, "decorator"),
            (Token.Name.Class, "type"),
            (Token.Name.Namespace, "type"),
            (Token.Name.Function, "name"),
            (Token.Name.Attribute, "name"),
            (Token.Literal.String, "string"),
            (Token.Literal.Number, "number"),
            (Token.Operator, "operator"),
            (Token.Punctuation, "text"),
            (Token.Name, "text"),
        ]

        out = []
        for token_type, value in lex(code, lexer):
            colour = theme["text"]
            for prefix, key in mapping:
                if token_type in prefix:
                    colour = theme[key]
                    break
            escaped = html.escape(value)
            if colour == theme["text"]:
                out.append(escaped)
            else:
                out.append(f'<span style="color:{colour}">{escaped}</span>')
        return "".join(out)
    except ImportError:
        return html.escape(code)


def _code_window(code: str, language: str, theme: dict, scale: float, label: str = "") -> str:
    dots = "".join(
        f'<span style="width:{int(20 * scale)}px;height:{int(20 * scale)}px;'
        f'border-radius:50%;background:{c};display:inline-block;"></span>'
        for c in ("#FF5F57", "#FEBC2E", "#28C840")
    )
    label_html = (
        f'<div style="font-size:{int(30 * scale)}px;font-weight:800;color:{theme["keyword"]};'
        f'margin:0 0 {int(16 * scale)}px 2px;">{html.escape(label)}</div>'
        if label
        else ""
    )
    return f"""
    {label_html}
    <div style="background:{theme["bg"]};border-radius:{int(16 * scale)}px;overflow:hidden;
                margin-bottom:{int(30 * scale)}px;">
      <div style="background:{theme["chrome"]};padding:{int(18 * scale)}px {int(22 * scale)}px;
                  display:flex;gap:{int(12 * scale)}px;align-items:center;">{dots}</div>
      <pre style="margin:0;padding:{int(34 * scale)}px;font-family:{MONO_STACK};
                  font-size:{int(26 * scale)}px;line-height:1.6;color:{theme["text"]};
                  white-space:pre-wrap;word-break:break-word;">{{CODE}}</pre>
    </div>""".replace("{CODE}", highlight_code(code, language, theme))


def render_code_card(payload: dict, style: dict, identity: dict, handle: str) -> str:
    """A code screenshot, optionally as a before/after pair."""
    scale = style["font_scale"]
    theme = CODE_THEMES.get(style.get("code_theme", "dark"), CODE_THEMES["dark"])
    language = payload.get("language", "java")

    title = payload.get("title", "")
    title_html = (
        f'<div style="font-size:{int(44 * scale)}px;font-weight:800;'
        f'margin:0 0 {int(32 * scale)}px 0;">{format_inline(title, style)}</div>'
        if title
        else ""
    )

    before = payload.get("before_code", "")
    after = payload.get("after_code", "")
    if before and after:
        windows = _code_window(
            before, language, theme, scale, payload.get("before_label", "before")
        ) + _code_window(
            after, language, theme, scale, payload.get("after_label", "after")
        )
    else:
        windows = _code_window(payload.get("code", ""), language, theme, scale)

    caption = payload.get("caption", "")
    caption_html = (
        f'<div style="font-size:{int(30 * scale)}px;line-height:1.45;color:{style["muted_color"]};'
        f'margin-top:{int(6 * scale)}px;">{format_inline(caption, style)}</div>'
        if caption
        else ""
    )

    card_style = dict(style)
    card_style["background"] = style.get("background") or theme["page"]
    return _shell(f"{title_html}{windows}{caption_html}", card_style)


# ─── Archetype 4: diagram ─────────────────────────────────────────

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"


def render_diagram(payload: dict, style: dict, identity: dict, handle: str,
                   mermaid_src: str = MERMAID_CDN) -> str:
    """An architecture or flow diagram drawn from Mermaid source.

    The LLM writes Mermaid rather than describing a picture, so the boxes and
    arrows are actually correct — something an image model cannot guarantee.
    """
    scale = style["font_scale"]
    diagram = payload.get("mermaid", "") or "flowchart LR\n  A[Start] --> B[End]"

    title = payload.get("title", "")
    title_html = (
        f'<div style="font-size:{int(44 * scale)}px;font-weight:800;text-align:center;'
        f'margin:0 0 {int(40 * scale)}px 0;">{format_inline(title, style)}</div>'
        if title
        else ""
    )
    caption = payload.get("caption", "")
    caption_html = (
        f'<div style="font-size:{int(28 * scale)}px;text-align:center;color:{style["muted_color"]};'
        f'margin-top:{int(36 * scale)}px;">{format_inline(caption, style)}</div>'
        if caption
        else ""
    )

    is_dark = style.get("code_theme", "dark") == "dark"
    head = f"""
<script src="{html.escape(mermaid_src)}"></script>
<script>
  window.__diagramReady = false;
  window.addEventListener('load', async () => {{
    try {{
      mermaid.initialize({{
        startOnLoad: false,
        theme: '{"dark" if is_dark else "default"}',
        themeVariables: {{
          primaryColor: '{style["accent_color"]}',
          fontFamily: "{FONT_STACK}",
          fontSize: '{int(20 * scale)}px'
        }},
        flowchart: {{ curve: 'basis', useMaxWidth: true }}
      }});
      await mermaid.run({{ querySelector: '.mermaid' }});
    }} catch (e) {{
      document.getElementById('diagram-error').textContent =
        'Diagram could not be drawn: ' + e.message;
    }}
    window.__diagramReady = true;
  }});
</script>"""

    body = f"""
      {title_html}
      <div class="mermaid" style="display:flex;justify-content:center;">{html.escape(diagram)}</div>
      <div id="diagram-error" style="color:{style["accent_color"]};font-size:{int(24 * scale)}px;
           text-align:center;"></div>
      {caption_html}"""
    return _shell(body, style, extra_head=head)


# ─── Dispatch ─────────────────────────────────────────────────────

_RENDERERS = {
    "social-card": render_social_card,
    "interview-card": render_interview_card,
    "code-card": render_code_card,
    "diagram": render_diagram,
}


def build_html(
    archetype: str,
    payload: dict,
    style: dict | None = None,
    identity: dict | None = None,
    handle: str = "",
) -> str:
    """Build the HTML for one card. Unknown archetypes fall back to the social card."""
    renderer = _RENDERERS.get(archetype, render_social_card)
    return renderer(payload or {}, merge_style(style), identity or {}, handle)
