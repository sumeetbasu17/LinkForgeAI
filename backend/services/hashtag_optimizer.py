"""
Hashtag Optimizer.
LinkedIn 2026: hashtags are for categorization, not discovery.
But the RIGHT 3-4 hashtags still signal topic DNA to the algorithm.
"""

from services.llm import llm_service
from services.research import research_service


class HashtagOptimizer:
    """Optimizes hashtags for LinkedIn's 2026 algorithm."""

    # Categorized hashtag pools by category
    HASHTAG_POOLS = {
        "ai-engineering": {
            "broad": ["AI", "MachineLearning", "ArtificialIntelligence", "GenerativeAI", "LLM"],
            "niche": ["RAG", "LangChain", "AIAgents", "PromptEngineering", "VectorDB", "MLOps", "AIEngineering"],
        },
        "system-design": {
            "broad": ["SystemDesign", "SoftwareArchitecture", "Engineering", "TechLeadership"],
            "niche": ["CQRS", "EventDriven", "Microservices", "DistributedSystems", "Scalability", "HLD"],
        },
        "clean-code": {
            "broad": ["Java", "Programming", "SoftwareEngineering", "CleanCode"],
            "niche": ["SOLID", "DesignPatterns", "CodeQuality", "Refactoring", "LLD", "OOP"],
        },
        "career-growth": {
            "broad": ["CareerGrowth", "TechCareers", "SoftwareDevelopment", "Leadership"],
            "niche": ["SeniorEngineer", "TechInterviews", "EngineeringCulture", "ICTrack", "CodingInterview"],
        },
        "productivity": {
            "broad": ["Productivity", "Engineering", "DeveloperLife", "TechLife"],
            "niche": ["DeepWork", "CodeReview", "DevTools", "EngineeringProductivity", "DeveloperWorkflow"],
        },
        "genai-tools": {
            "broad": ["AI", "GenerativeAI", "TechTools", "Innovation"],
            "niche": ["ClaudeAI", "ChatGPT", "CopilotAI", "AITools", "LLMBenchmarks", "AIReview"],
        },
        "tech-concepts": {
            "broad": ["Technology", "SoftwareEngineering", "Backend", "TechExplainer"],
            "niche": ["EventSourcing", "DatabaseDesign", "Concurrency", "APIDesign", "Caching", "MessageQueues"],
        },
    }

    async def optimize(
        self,
        post_content: str,
        category: str,
        count: int = 4,
    ) -> dict:
        """Pick optimal hashtags for a post.

        Strategy: 1 broad (reach) + 2 niche (relevance) + 1 contextual (from content)

        Returns:
        {
            "hashtags": ["#Tag1", "#Tag2", ...],
            "reasoning": str,
            "strategy": "1 broad + 2 niche + 1 contextual"
        }
        """
        pool = self.HASHTAG_POOLS.get(category, self.HASHTAG_POOLS.get("tech-concepts", {}))
        broad = pool.get("broad", [])
        niche = pool.get("niche", [])

        system_prompt = """You select optimal LinkedIn hashtags.

LinkedIn 2026 rules:
- Hashtags signal topic DNA to the algorithm
- 3-4 hashtags is optimal (more = spammy)
- Mix: 1 broad (reach) + 2 niche (relevance) + 1 contextual (from content)
- Never put hashtags in comments (algorithm ignores them there)
- Use CamelCase for readability"""

        user_prompt = f"""Post content:
{post_content[:400]}

Category: {category}
Available broad hashtags: {', '.join(broad)}
Available niche hashtags: {', '.join(niche)}

Pick exactly {count} hashtags. You can suggest new contextual ones not in the lists.

Return JSON:
{{
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4"],
  "reasoning": "why these 4 work together (1 sentence)"
}}"""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=True)
            tags = result.get("hashtags", [])
            # Ensure # prefix
            tags = [t if t.startswith("#") else f"#{t}" for t in tags]
            return {
                "hashtags": tags[:count],
                "reasoning": result.get("reasoning", ""),
                "strategy": f"1 broad + {count - 2} niche + 1 contextual",
            }
        except Exception:
            # Fallback: pick 1 broad + 2 niche
            fallback = []
            if broad:
                fallback.append(f"#{broad[0]}")
            for tag in niche[:count - 1]:
                fallback.append(f"#{tag}")
            return {
                "hashtags": fallback[:count],
                "reasoning": "Fallback selection from category pool",
                "strategy": "auto-selected",
            }


hashtag_optimizer = HashtagOptimizer()
