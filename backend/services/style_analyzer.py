"""
Style analyzer service.
Extracts writing patterns from user's past posts to build a style profile.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from services.llm import llm_service


@dataclass
class StyleProfile:
    """Captured writing style from a user's posts."""

    avg_word_count: int = 0
    avg_paragraph_count: int = 0
    avg_sentence_length: float = 0.0
    uses_code_blocks: bool = False
    uses_arrow_bullets: bool = False
    uses_emoji: bool = False
    emoji_style: str = ""  # e.g. "strategic (→, ✅, 🔴)" or "none"
    hook_style: str = ""  # e.g. "bold statement", "question", "story opener"
    cta_style: str = ""  # e.g. "question-based", "share your experience", "none"
    hashtag_count: int = 0
    formatting_style: str = ""  # e.g. "short paragraphs with arrows"
    voice_description: str = ""  # LLM-generated description of their voice
    tone_keywords: list = field(default_factory=list)
    sample_hooks: list = field(default_factory=list)
    sample_ctas: list = field(default_factory=list)

    def to_prompt_string(self) -> str:
        """Convert style profile to a string for LLM prompts."""
        parts = [
            f"Average post length: ~{self.avg_word_count} words",
            f"Paragraphs per post: ~{self.avg_paragraph_count}",
            f"Voice: {self.voice_description}",
            f"Hook style: {self.hook_style}",
            f"CTA style: {self.cta_style}",
            f"Formatting: {self.formatting_style}",
            f"Emoji usage: {self.emoji_style}",
            f"Hashtags: ~{self.hashtag_count} per post",
        ]
        if self.uses_code_blocks:
            parts.append("Includes code blocks in technical posts")
        if self.sample_hooks:
            parts.append(f"Example hooks: {'; '.join(self.sample_hooks[:3])}")
        if self.tone_keywords:
            parts.append(f"Tone keywords: {', '.join(self.tone_keywords)}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)


class StyleAnalyzer:
    """Analyzes posts to extract writing style patterns."""

    def analyze_posts_basic(self, posts: list[str]) -> StyleProfile:
        """Extract basic style metrics from posts without LLM."""
        if not posts:
            return StyleProfile()

        word_counts = []
        paragraph_counts = []
        sentence_lengths = []
        has_code = False
        has_arrows = False
        has_emoji = False
        hashtag_counts = []

        emoji_pattern = re.compile(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
            r"\U00002702-\U000027B0\U0001F900-\U0001F9FF"
            r"→✅✓●▶◆★☆♦►▪▸]",
            re.UNICODE,
        )

        for post in posts:
            words = post.split()
            word_counts.append(len(words))

            paragraphs = [p.strip() for p in post.split("\n\n") if p.strip()]
            paragraph_counts.append(len(paragraphs))

            sentences = re.split(r"[.!?]+", post)
            for s in sentences:
                s_words = s.split()
                if len(s_words) > 2:
                    sentence_lengths.append(len(s_words))

            if "```" in post or "    " in post:
                has_code = True
            if "→" in post or "➡" in post:
                has_arrows = True

            emojis_found = emoji_pattern.findall(post)
            if emojis_found:
                has_emoji = True

            hashtags = re.findall(r"#\w+", post)
            hashtag_counts.append(len(hashtags))

        profile = StyleProfile(
            avg_word_count=int(sum(word_counts) / len(word_counts)) if word_counts else 0,
            avg_paragraph_count=int(sum(paragraph_counts) / len(paragraph_counts)) if paragraph_counts else 0,
            avg_sentence_length=round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0,
            uses_code_blocks=has_code,
            uses_arrow_bullets=has_arrows,
            uses_emoji=has_emoji,
            hashtag_count=int(sum(hashtag_counts) / len(hashtag_counts)) if hashtag_counts else 0,
        )
        return profile

    async def analyze_posts_full(self, posts: list[str]) -> StyleProfile:
        """Full style analysis using basic metrics + LLM for voice description."""
        profile = self.analyze_posts_basic(posts)

        if not posts:
            return profile

        # Use LLM to understand voice, hook style, CTA style
        sample_posts = posts[:5]  # Use up to 5 posts for analysis
        posts_text = "\n\n---POST SEPARATOR---\n\n".join(sample_posts)

        system_prompt = """You are a writing style analyst. Analyze the provided LinkedIn posts 
and extract the author's unique writing patterns. Respond ONLY with valid JSON."""

        user_prompt = f"""Analyze these LinkedIn posts and describe the writing style:

{posts_text}

Return JSON with these fields:
{{
  "voice_description": "2-3 sentence description of their writing voice and personality",
  "hook_style": "how they start posts (e.g., 'bold contrarian statement', 'personal story opener', 'question')",
  "cta_style": "how they end posts (e.g., 'asks a question', 'invites sharing experience', 'none')",
  "formatting_style": "how they format text (e.g., 'short paragraphs with arrow bullets', 'numbered lists')",
  "emoji_style": "their emoji usage pattern (e.g., 'strategic arrows and checkmarks', 'heavy emoji use', 'minimal')",
  "tone_keywords": ["list", "of", "3-5", "tone", "words"],
  "sample_hooks": ["first line of post 1", "first line of post 2", "first line of post 3"]
}}"""

        try:
            result = await llm_service.call_structured(
                system_prompt, user_prompt, light=True
            )
            profile.voice_description = result.get("voice_description", "")
            profile.hook_style = result.get("hook_style", "")
            profile.cta_style = result.get("cta_style", "")
            profile.formatting_style = result.get("formatting_style", profile.formatting_style)
            profile.emoji_style = result.get("emoji_style", "")
            profile.tone_keywords = result.get("tone_keywords", [])
            profile.sample_hooks = result.get("sample_hooks", [])
        except Exception as e:
            # If LLM fails, we still have the basic analysis
            profile.voice_description = "Analysis pending"
            profile.hook_style = "bold statement" if profile.uses_arrow_bullets else "mixed"
            profile.emoji_style = "moderate" if profile.uses_emoji else "minimal"

        return profile


# Singleton
style_analyzer = StyleAnalyzer()
