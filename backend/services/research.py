"""
Web research service using Tavily API.
Fetches trending topics and gathers facts for post generation.
"""

import httpx
from typing import Optional

from config.settings import settings


class ResearchService:
    """Tavily-powered web research for trending topics and facts."""

    def __init__(self):
        self.api_key = settings.TAVILY_API_KEY
        self.base_url = "https://api.tavily.com"

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_answer: bool = True,
    ) -> dict:
        """Search the web for a query. Returns structured results."""
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/search", json=payload)
            response.raise_for_status()
            return response.json()

    async def find_trending_topics(
        self, category: str, category_description: str
    ) -> list[dict]:
        """Find trending topics for a given category.

        Returns list of:
          {"title": str, "summary": str, "url": str, "relevance": str}
        """
        query = (
            f"latest trending topics in {category}: {category_description} "
            f"for software engineers LinkedIn 2025 2026"
        )
        result = await self.search(query, max_results=8)

        topics = []
        for item in result.get("results", []):
            topics.append(
                {
                    "title": item.get("title", ""),
                    "summary": item.get("content", "")[:300],
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                }
            )
        return topics

    async def research_topic(self, topic: str) -> dict:
        """Deep research on a specific topic. Returns facts and context."""
        result = await self.search(
            query=f"{topic} latest developments insights data",
            max_results=5,
            search_depth="advanced",
            include_answer=True,
        )

        facts = []
        for item in result.get("results", []):
            facts.append(
                {
                    "source": item.get("title", ""),
                    "content": item.get("content", "")[:500],
                    "url": item.get("url", ""),
                }
            )

        return {
            "answer": result.get("answer", ""),
            "facts": facts,
            "query": topic,
        }


# Singleton
research_service = ResearchService()
