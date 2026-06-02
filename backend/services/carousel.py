"""
Carousel Generator Service.
Converts LinkedIn posts into PDF carousel slides.
LinkedIn carousels (uploaded as PDFs) get 3x more reach than text-only posts.
"""

import json
from services.llm import llm_service


class CarouselGenerator:
    """Converts a post into carousel slide content."""

    async def generate_slides(self, post_content: str, num_slides: int = 8) -> list[dict]:
        """Break a post into carousel slides.

        Returns list of {"slide_number": int, "headline": str, "body": str, "type": str}
        type can be: "cover", "content", "cta"
        """
        system_prompt = """You convert LinkedIn posts into carousel slides.
Each slide should have a punchy headline (5-8 words) and body text (15-25 words max).
The first slide is the cover (hook), the last slide is the CTA.
Middle slides break down the key points.

RULES:
1. Cover slide: bold claim or question that makes people swipe
2. Each content slide: ONE idea, ONE takeaway
3. Use numbers and arrows (→) for clarity
4. CTA slide: ask a question + "Follow for more"
5. Keep text SHORT — carousels are visual, not essays"""

        user_prompt = f"""Convert this LinkedIn post into {num_slides} carousel slides:

{post_content}

Return JSON array:
[
  {{"slide_number": 1, "headline": "...", "body": "...", "type": "cover"}},
  {{"slide_number": 2, "headline": "...", "body": "...", "type": "content"}},
  ...
  {{"slide_number": {num_slides}, "headline": "...", "body": "...", "type": "cta"}}
]"""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=False)
            if isinstance(result, list):
                return result
            return result.get("slides", [])
        except Exception as e:
            # Fallback: simple paragraph-based splitting
            paragraphs = [p.strip() for p in post_content.split("\n\n") if p.strip()]
            slides = [{"slide_number": 1, "headline": paragraphs[0][:60] if paragraphs else "Title", "body": "", "type": "cover"}]
            for i, para in enumerate(paragraphs[1:], 2):
                slides.append({"slide_number": i, "headline": para[:40], "body": para[40:100], "type": "content"})
            slides.append({"slide_number": len(slides) + 1, "headline": "What do you think?", "body": "Follow for more insights →", "type": "cta"})
            return slides[:num_slides]


carousel_generator = CarouselGenerator()
