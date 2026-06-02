"""
Hook A/B Tester.
Generates multiple hook variations for a post and predicts which will perform best.
The first 2 lines of a LinkedIn post determine if people click "see more".
"""

from services.llm import llm_service


class HookTester:
    """Generate and score multiple hook variations."""

    HOOK_FORMULAS = [
        "bold_claim",       # "Most teams don't need microservices."
        "question",         # "What if everything you know about scaling is wrong?"
        "story_opener",     # "Last Tuesday at 2 AM, our production DB went down."
        "data_point",       # "We reduced latency by 73%. Here's the one change."
        "contrarian",       # "Unpopular opinion: clean code is overrated."
        "curiosity_gap",    # "I spent 6 months building the wrong thing. Here's why."
    ]

    async def generate_hooks(self, post_content: str, count: int = 3) -> list[dict]:
        """Generate multiple hook variations for a post.

        Returns list of:
        {
            "hook": str (the first 2 lines),
            "formula": str (which formula it uses),
            "predicted_score": int (0-100),
            "reasoning": str
        }
        """
        system_prompt = """You are a LinkedIn hook expert. The first 2 lines of a post 
determine if people click "see more" — this is the most important part.

Generate hooks using different formulas:
- Bold claim: Start with a provocative statement
- Question: Ask something that makes them think
- Story opener: Drop them into a moment
- Data point: Lead with a specific number
- Contrarian: Challenge conventional wisdom
- Curiosity gap: Tease what they'll learn

Score each hook 0-100 based on:
- Stop-scroll power (would someone pause scrolling?)
- Curiosity creation (do they NEED to read more?)
- Specificity (vague = boring, specific = compelling)
- Emotional resonance (does it trigger a feeling?)"""

        user_prompt = f"""Post content (write hooks for this):
{post_content[:500]}

Generate {count} different hooks using different formulas.

Return JSON array:
[
  {{
    "hook": "the first 2 lines of the post",
    "formula": "which formula (bold_claim, question, story_opener, data_point, contrarian, curiosity_gap)",
    "predicted_score": 85,
    "reasoning": "why this hook works (1 sentence)"
  }}
]

Order by predicted_score descending (best first)."""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=False)
            hooks = result if isinstance(result, list) else result.get("hooks", [])
            # Sort by score
            hooks.sort(key=lambda h: h.get("predicted_score", 0), reverse=True)
            return hooks[:count]
        except Exception:
            return [{"hook": post_content.split("\n")[0][:100], "formula": "original", "predicted_score": 50, "reasoning": "Original hook (generation failed)"}]

    async def apply_best_hook(self, post_content: str, hook: str) -> str:
        """Replace the post's opening with the chosen hook."""
        lines = post_content.split("\n")
        # Find where the actual content starts (skip empty lines at top)
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip():
                # Skip the first 1-2 non-empty lines (existing hook)
                content_start = i + 1
                # If next line is also non-empty and short, skip it too
                if i + 1 < len(lines) and lines[i + 1].strip() and len(lines[i + 1]) < 80:
                    content_start = i + 2
                break

        remaining = "\n".join(lines[content_start:])
        return f"{hook}\n\n{remaining}"


hook_tester = HookTester()
