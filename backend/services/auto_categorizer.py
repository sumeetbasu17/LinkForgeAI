"""
Auto-categorization service.
Classifies articles into categories using LLM when no category is manually selected.
"""

from services.llm import llm_service
from config.settings import settings


class AutoCategorizer:
    """Classifies articles into predefined categories."""

    def _get_category_list(self) -> str:
        """Build a string of available categories for the LLM prompt."""
        cats = settings.DEFAULT_CATEGORIES
        lines = []
        for c in cats:
            lines.append(f'- "{c["id"]}": {c["label"]} \u2014 {c["description"]}')
        return "\n".join(lines)

    async def categorize_single(self, content: str) -> str:
        """Classify a single article into one category.

        Returns the category ID string (e.g., "career-growth").
        """
        if not content or len(content.strip()) < 20:
            return ""

        categories_str = self._get_category_list()

        system_prompt = """You classify LinkedIn posts into categories. 
Read the post and pick the SINGLE best matching category from the list.
Respond with ONLY the category ID string, nothing else. No quotes, no explanation."""

        user_prompt = f"""Categories:
{categories_str}

Post to classify:
{content[:500]}

Which category ID best fits this post? Reply with just the ID (e.g., career-growth):"""

        try:
            result = await llm_service.call_light(
                system_prompt, user_prompt, temperature=0.1,
            )
            # Clean the response
            cat_id = result.strip().strip('"').strip("'").lower()

            # Validate it's a real category
            valid_ids = [c["id"] for c in settings.DEFAULT_CATEGORIES]
            if cat_id in valid_ids:
                return cat_id

            # Try partial match (LLM might return "career growth" instead of "career-growth")
            for vid in valid_ids:
                if vid.replace("-", "") in cat_id.replace("-", "").replace(" ", ""):
                    return vid

            # Default fallback
            return ""
        except Exception:
            return ""

    async def categorize_batch(self, articles: list[str]) -> list[str]:
        """Classify multiple articles at once.

        For efficiency, sends up to 10 articles in a single LLM call.
        Falls back to individual calls if batch fails.

        Returns list of category IDs in same order as input.
        """
        if not articles:
            return []

        # For small batches, do individual calls
        if len(articles) <= 3:
            results = []
            for art in articles:
                cat = await self.categorize_single(art)
                results.append(cat)
            return results

        # For larger batches, try batch classification
        categories_str = self._get_category_list()

        # Prepare article summaries (first 200 chars each)
        article_list = []
        for i, art in enumerate(articles[:20]):  # Cap at 20
            preview = art.strip()[:200].replace("\n", " ")
            article_list.append(f"Article {i+1}: {preview}")

        articles_text = "\n\n".join(article_list)

        system_prompt = """You classify LinkedIn posts into categories.
For each article, pick the SINGLE best matching category from the list.
Respond with ONLY a JSON array of category IDs, in the same order as the articles.
No explanation, no markdown. Just the JSON array."""

        user_prompt = f"""Categories:
{categories_str}

Articles to classify:
{articles_text}

Return a JSON array with one category ID per article. Example: ["career-growth", "system-design", "ai-engineering"]
Reply:"""

        try:
            result = await llm_service.call_structured(
                system_prompt, user_prompt, light=True,
            )

            if isinstance(result, list):
                valid_ids = [c["id"] for c in settings.DEFAULT_CATEGORIES]
                # Validate and clean each result
                cleaned = []
                for cat in result:
                    cat_id = str(cat).strip().strip('"').lower()
                    if cat_id in valid_ids:
                        cleaned.append(cat_id)
                    else:
                        cleaned.append("")
                # Pad if LLM returned fewer than expected
                while len(cleaned) < len(articles):
                    cleaned.append("")
                return cleaned[:len(articles)]

            # Unexpected format, fall back to individual
            raise ValueError("Batch response not a list")

        except Exception:
            # Fallback: classify individually
            results = []
            for art in articles:
                cat = await self.categorize_single(art)
                results.append(cat)
            return results


auto_categorizer = AutoCategorizer()
