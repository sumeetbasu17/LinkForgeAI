"""
Auto-categorization service.

Classifies articles into the configured categories when the user uploads with
"Auto-detect" instead of picking a category by hand.

Every article that goes in must come out with a category. The previous version
truncated the batch prompt at 20 articles and padded the rest with empty
strings, so a 50-article upload silently left 30 posts uncategorized.
"""

import asyncio

from config.settings import settings
from services.llm import llm_service

# Articles per LLM request. Small enough that the model keeps track of the
# ordering, large enough to keep the call count (and cost) down.
BATCH_SIZE = 10

# Concurrent LLM requests. Keeps big uploads fast without tripping rate limits.
MAX_CONCURRENCY = 4

# How much of each article the classifier sees. The opening lines carry the
# topic; the tail is usually hashtags and a link.
PREVIEW_CHARS = 700


class AutoCategorizer:
    """Classifies articles into predefined categories."""

    def _valid_ids(self) -> list[str]:
        return [c["id"] for c in settings.DEFAULT_CATEGORIES]

    def _fallback_id(self) -> str:
        """Category used only when the LLM is unreachable or unusable."""
        fallback = getattr(settings, "FALLBACK_CATEGORY", "")
        valid = self._valid_ids()
        if fallback in valid:
            return fallback
        return valid[0] if valid else ""

    def _get_category_list(self) -> str:
        """Build a string of available categories for the LLM prompt."""
        lines = []
        for c in settings.DEFAULT_CATEGORIES:
            lines.append(f'- "{c["id"]}": {c["label"]} — {c["description"]}')
        return "\n".join(lines)

    def _normalize(self, raw: str) -> str:
        """Map a model response onto a real category ID, or return ''."""
        if not raw:
            return ""
        cat_id = str(raw).strip().strip('"').strip("'").strip().lower()
        valid = self._valid_ids()
        if cat_id in valid:
            return cat_id

        # Tolerate spacing and underscore variants ("career growth").
        squashed = cat_id.replace("-", "").replace("_", "").replace(" ", "")
        for vid in valid:
            if vid.replace("-", "") == squashed:
                return vid
        for vid in valid:
            if vid.replace("-", "") in squashed:
                return vid

        # Last resort: match on the human-readable label.
        for c in settings.DEFAULT_CATEGORIES:
            if c["label"].lower() in cat_id:
                return c["id"]
        return ""

    # ─── Single article ───────────────────────────────────────────

    async def categorize_single(self, content: str) -> str:
        """Classify one article. Returns a category ID, or '' if unusable."""
        if not content or len(content.strip()) < 20:
            return ""

        system_prompt = (
            "You classify LinkedIn posts into categories.\n"
            "Read the post and pick the SINGLE best matching category.\n"
            "Every post must be assigned a category. If the fit is imperfect, "
            "choose the closest one anyway — never refuse and never invent a "
            "new category.\n"
            "Respond with ONLY the category ID string. No quotes, no explanation."
        )
        user_prompt = f"""Categories:
{self._get_category_list()}

Post to classify:
{content[:PREVIEW_CHARS]}

Which category ID best fits this post? Reply with just the ID (e.g., career-growth):"""

        try:
            result = await llm_service.call_light(
                system_prompt, user_prompt, temperature=0.1,
            )
            return self._normalize(result)
        except Exception:
            return ""

    # ─── Batches ──────────────────────────────────────────────────

    async def _categorize_chunk(self, chunk: list[str]) -> list[str]:
        """Classify up to BATCH_SIZE articles in one call.

        The model answers with an index -> category map rather than a bare
        array, so a missing or extra entry can never shift every following
        article onto the wrong category.
        """
        numbered = []
        for i, art in enumerate(chunk, start=1):
            preview = " ".join(art.split())[:PREVIEW_CHARS]
            numbered.append(f"[{i}]\n{preview}")
        articles_text = "\n\n".join(numbered)

        system_prompt = (
            "You classify LinkedIn posts into categories.\n"
            "For each numbered post, pick the SINGLE best matching category.\n"
            "Every post must get a category. If the fit is imperfect, choose "
            "the closest one anyway — never leave one out, never return an "
            "empty value, never invent a new category.\n"
            'Respond with ONLY a JSON object mapping the post number to the '
            'category ID, e.g. {"1": "career-growth", "2": "system-design"}.'
        )
        user_prompt = f"""Categories:
{self._get_category_list()}

Posts to classify:
{articles_text}

Return a JSON object with one entry per post number (1 to {len(chunk)}):"""

        result = await llm_service.call_structured(
            system_prompt, user_prompt, light=True,
        )

        out = [""] * len(chunk)
        if isinstance(result, dict):
            for key, value in result.items():
                try:
                    idx = int(str(key).strip().strip("[]")) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(chunk):
                    out[idx] = self._normalize(value)
        elif isinstance(result, list):
            # Tolerate a model that answers with a plain array anyway.
            for idx, value in enumerate(result[: len(chunk)]):
                out[idx] = self._normalize(value)
        return out

    async def categorize_batch(self, articles: list[str]) -> list[str]:
        """Classify any number of articles.

        Runs in three passes so nothing is silently dropped:
          1. Batched requests, several in flight at once.
          2. Anything a batch missed is retried on its own.
          3. Anything still unresolved falls back to the default category.

        Returns one category ID per input article, in the same order.
        """
        if not articles:
            return []

        results: list[str] = [""] * len(articles)
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        chunks = [
            (start, articles[start : start + BATCH_SIZE])
            for start in range(0, len(articles), BATCH_SIZE)
        ]

        async def run_chunk(start: int, chunk: list[str]) -> None:
            async with semaphore:
                try:
                    cats = await self._categorize_chunk(chunk)
                except Exception:
                    cats = [""] * len(chunk)
            for offset, cat in enumerate(cats):
                results[start + offset] = cat

        await asyncio.gather(*(run_chunk(s, c) for s, c in chunks))

        # Pass 2 — retry the stragglers individually.
        missing = [i for i, cat in enumerate(results) if not cat]

        async def run_single(index: int) -> None:
            async with semaphore:
                try:
                    results[index] = await self.categorize_single(articles[index])
                except Exception:
                    results[index] = ""

        if missing:
            await asyncio.gather(*(run_single(i) for i in missing))

        # Pass 3 — never hand back a blank for a real article.
        fallback = self._fallback_id()
        for i, cat in enumerate(results):
            if not cat and articles[i] and len(articles[i].strip()) >= 20:
                results[i] = fallback

        return results


auto_categorizer = AutoCategorizer()
