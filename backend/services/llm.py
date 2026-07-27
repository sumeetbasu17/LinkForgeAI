"""
LLM service wrapper using OpenRouter.
Model is read from user preferences in the database.
Falls back to settings.py defaults only if no preference is set.
"""

import json
import httpx
from typing import Optional

from config.settings import settings

# Default fallbacks (used only if user hasn't selected a model)
_DEFAULT_HEAVY = "anthropic/claude-sonnet-4.5"
_DEFAULT_LIGHT = "anthropic/claude-haiku-4.5"


class LLMService:
    """OpenRouter LLM wrapper. Reads model from user prefs."""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL

    def _get_user_model(self, user_id: str = "default") -> str:
        """Get user's preferred model from database. Returns model ID string."""
        try:
            from db.database import database
            prefs = database.get_preferences(user_id)
            model = prefs.get("preferred_model", "")
            if model and model.strip():
                return model.strip()
        except Exception:
            pass
        # Fallback to .env or hardcoded default
        return settings.LLM_MODEL or _DEFAULT_HEAVY

    async def _call(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Make a call to OpenRouter API."""
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file. "
                "Get a free key at https://openrouter.ai/keys"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://linkedin-post-generator.app",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                try:
                    err = response.json()
                    err_msg = err.get("error", {}).get("message", response.text[:300])
                except Exception:
                    err_msg = response.text[:300]
                raise ValueError(
                    f"OpenRouter error ({response.status_code}): {err_msg}. "
                    f"Model: {model}. Check your API key and credits at openrouter.ai"
                )

            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def call_heavy(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        user_id: str = "default",
    ) -> str:
        """Heavy LLM call — uses user's selected model."""
        model = self._get_user_model(user_id)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self._call(messages, model, temperature)

    async def call_light(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        user_id: str = "default",
    ) -> str:
        """Light LLM call — uses a fast model for quick tasks."""
        # For light calls, use haiku regardless of user preference
        # (saves money on topic selection, quality checks)
        model = settings.LLM_MODEL_LIGHT or _DEFAULT_LIGHT
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self._call(messages, model, temperature, max_tokens=1000)

    async def call_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        image_data_uri: str,
        temperature: float = 0.2,
    ) -> str:
        """Send an image plus a prompt to a vision-capable model.

        Used once per uploaded inspiration image to extract a reusable style
        preset — never on the hot path of post generation.
        """
        model = settings.VISION_MODEL or _DEFAULT_HEAVY
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            },
        ]
        return await self._call(messages, model, temperature, max_tokens=1500)

    async def call_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        light: bool = True,
        user_id: str = "default",
    ) -> dict:
        """LLM call that expects JSON response."""
        if light:
            model = settings.LLM_MODEL_LIGHT or _DEFAULT_LIGHT
        else:
            model = self._get_user_model(user_id)

        system_prompt += (
            "\n\nIMPORTANT: Respond ONLY with valid JSON. "
            "No markdown, no backticks, no explanation. Just the JSON object."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw = await self._call(messages, model, temperature=0.3)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        return json.loads(cleaned)


# Singleton
llm_service = LLMService()
