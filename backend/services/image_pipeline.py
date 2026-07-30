"""Render a card for a post using the settings from the Images tab.

Both the Editor (POST /api/images/generate) and the autonomous scheduler go
through here, so an auto-published post gets exactly the same treatment as one
rendered by hand: the same enabled preset, the same handle rotation, the same
identity. Before this existed the scheduler dropped the visual step entirely and
every autonomous post went out as plain text.
"""

from __future__ import annotations

import uuid
from typing import Optional

from db.database import database
from services.image_renderer import image_renderer


def pick_preset(
    user_id: str, archetype: str, preset_id: str = ""
) -> tuple[Optional[dict], str]:
    """Resolve the style preset to render with.

    Order: the explicitly requested preset, then any enabled preset learned for
    this archetype in the Images tab, then None for the built-in defaults.
    Returns (style, preset_id).
    """
    presets = database.list_image_presets(user_id)
    if preset_id:
        match = next((p for p in presets if p["id"] == preset_id), None)
        if not match:
            raise LookupError("Preset not found")
        return match["style"], preset_id

    match = next(
        (p for p in presets if p["archetype"] == archetype and p["enabled"]), None
    )
    if match:
        return match["style"], match["id"]
    return None, ""


async def render_for_post(
    archetype: str,
    payload: dict,
    user_id: str = "default",
    post_id: str = "",
    preset_id: str = "",
    handle: str = "",
) -> dict:
    """Render a card, store it, and return its record.

    Raises RendererUnavailable (no renderer installed), LookupError (unknown
    preset) or Exception (render failure) — callers decide how loud to be.
    """
    archetype = archetype or "social-card"
    style, preset_id = pick_preset(user_id, archetype, preset_id)

    identity = database.get_image_identity(user_id)

    # Only the person-shaped cards carry a handle.
    if archetype in ("social-card", "interview-card"):
        handle = handle or database.pick_image_handle(
            user_id, identity.get("handle_strategy", "round-robin")
        )
    else:
        handle = ""

    path = await image_renderer.render_card(archetype, payload, style, identity, handle)

    image_id = f"img_{uuid.uuid4().hex[:10]}"
    database.add_post_image(
        image_id=image_id,
        archetype=archetype,
        file_path=str(path),
        post_id=post_id,
        preset_id=preset_id,
        handle=handle,
        payload=payload,
        user_id=user_id,
    )

    return {
        "id": image_id,
        "archetype": archetype,
        "handle": handle,
        "preset_id": preset_id,
        "payload": payload,
        "path": path,
        "url": f"/api/images/file/{path.name}",
    }
