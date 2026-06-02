"""
Content Repurposer.
Turns one LinkedIn post into multiple formats:
- Twitter/X thread
- Newsletter section
- Blog intro
- Short-form video script

One piece of content → 4 distribution channels.
"""

from services.llm import llm_service


class ContentRepurposer:
    """Repurpose LinkedIn posts into other content formats."""

    async def repurpose(self, post_content: str, title: str = "", formats: list[str] = None) -> dict:
        """Repurpose a post into multiple formats.

        formats: list of target formats. Default: all.
        Available: "twitter_thread", "newsletter", "blog_intro", "video_script"

        Returns dict of {format_name: content_string}
        """
        if formats is None:
            formats = ["twitter_thread", "newsletter", "blog_intro", "video_script"]

        format_instructions = {
            "twitter_thread": """Twitter/X thread (5-8 tweets):
- First tweet: the hook (must work standalone)
- Each tweet: 1 idea, under 280 chars
- Last tweet: CTA + "Follow for more"
- Use 🧵 emoji on first tweet
- Number each tweet (1/, 2/, etc.)""",

            "newsletter": """Newsletter section (200-300 words):
- Opening paragraph that hooks email readers
- 2-3 subheadings with key insights
- Closing with a personal reflection
- More depth than the LinkedIn post
- Conversational but polished tone""",

            "blog_intro": """Blog post introduction (150-200 words):
- SEO-friendly opening paragraph
- Sets up the problem the full blog will solve
- Includes a "what you'll learn" promise
- Transitions into the main content
- End with "Let's dive in." or similar""",

            "video_script": """Short-form video script (60-90 seconds):
- Hook in first 3 seconds (bold claim)
- 3 key points, spoken conversationally
- Include [PAUSE] markers for emphasis
- End with CTA: "Follow for more" + question
- Write as spoken word, not written text
- Include [GESTURE] and [SHOW SCREEN] cues where relevant""",
        }

        results = {}
        for fmt in formats:
            if fmt not in format_instructions:
                continue

            system_prompt = f"""You repurpose LinkedIn content into other formats.
Maintain the same insights and voice but adapt for the target format.
Do NOT just copy-paste — each format has different conventions."""

            user_prompt = f"""Original LinkedIn post:
{post_content}

Convert to: {fmt.replace('_', ' ')}

Instructions:
{format_instructions[fmt]}

Return JSON: {{"{fmt}": "the repurposed content"}}"""

            try:
                result = await llm_service.call_structured(system_prompt, user_prompt, light=False)
                results[fmt] = result.get(fmt, "")
            except Exception:
                results[fmt] = f"[Repurposing failed for {fmt}]"

        return results


content_repurposer = ContentRepurposer()
