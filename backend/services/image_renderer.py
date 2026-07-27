"""
Renders card HTML to PNG with headless Chromium (Playwright).

Runs on the backend rather than in the browser so scheduled auto-posting can
produce images with no UI open.

Setup (also handled in the Dockerfile):
    pip install playwright
    playwright install --with-deps chromium
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from config.settings import settings
from services import image_templates

# Retina scale. LinkedIn downsamples, so rendering at 2x keeps text crisp.
DEVICE_SCALE = 2

# Diagrams need Mermaid to run before the screenshot is taken.
DIAGRAM_TIMEOUT_MS = 15000


class RendererUnavailable(RuntimeError):
    """Playwright or its browser binary is not installed."""


def media_dir() -> Path:
    path = Path(getattr(settings, "MEDIA_DIR", "./data/media"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class ImageRenderer:
    """Turns card HTML into a PNG on disk."""

    _launch_lock = asyncio.Lock()

    async def render_html(self, html: str, out_path: Path, wait_for_diagram: bool = False) -> Path:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RendererUnavailable(
                "Playwright is not installed. Run: pip install playwright && "
                "playwright install --with-deps chromium"
            ) from exc

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(args=["--no-sandbox", "--font-render-hinting=none"])
            except Exception as exc:
                raise RendererUnavailable(
                    f"Could not start Chromium: {exc}. "
                    "Run: playwright install --with-deps chromium"
                ) from exc

            try:
                page = await browser.new_page(
                    viewport={"width": image_templates.CARD_WIDTH, "height": 1200},
                    device_scale_factor=DEVICE_SCALE,
                )
                await page.set_content(html, wait_until="networkidle")

                if wait_for_diagram:
                    try:
                        await page.wait_for_function(
                            "window.__diagramReady === true", timeout=DIAGRAM_TIMEOUT_MS
                        )
                    except Exception:
                        # Mermaid could not load (offline CDN). The card still
                        # renders, showing the error line instead of a diagram.
                        pass

                # Let webfonts settle so text isn't captured mid-swap.
                await page.evaluate("document.fonts && document.fonts.ready")

                card = await page.query_selector("#card")
                if card is None:
                    raise RuntimeError("Card element missing from rendered HTML")

                out_path.parent.mkdir(parents=True, exist_ok=True)
                await card.screenshot(path=str(out_path), type="png")
            finally:
                await browser.close()

        return out_path

    async def render_card(
        self,
        archetype: str,
        payload: dict,
        style: dict | None = None,
        identity: dict | None = None,
        handle: str = "",
        filename: str = "",
    ) -> Path:
        """Build the HTML for an archetype and screenshot it."""
        html = image_templates.build_html(archetype, payload, style, identity, handle)
        name = filename or f"{archetype}_{uuid.uuid4().hex[:10]}.png"
        out_path = media_dir() / name
        # Chromium launches are heavy; serialise them so a bulk render doesn't
        # spawn a browser per card.
        async with self._launch_lock:
            return await self.render_html(
                html, out_path, wait_for_diagram=(archetype == "diagram")
            )


image_renderer = ImageRenderer()
