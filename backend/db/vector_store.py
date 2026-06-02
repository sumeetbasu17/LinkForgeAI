"""
Vector store using LanceDB for style embeddings and content similarity.
Stores user posts as embeddings for style matching during generation.
"""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

import lancedb
import numpy as np

from config.settings import settings


class VectorStore:
    """LanceDB-based vector store for post embeddings."""

    def __init__(self):
        self.db_path = settings.VECTOR_DB_PATH
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(self.db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        existing = self.db.table_names()

        if "user_posts" not in existing:
            self.db.create_table(
                "user_posts",
                data=[
                    {
                        "id": "init",
                        "user_id": "system",
                        "content": "initialization record",
                        "category": "system",
                        "post_type": "system",  # "own" or "inspiration"
                        "vector": np.zeros(384).tolist(),
                        "created_at": datetime.now().isoformat(),
                    }
                ],
            )

    def _simple_embedding(self, text: str) -> list[float]:
        """Generate a simple embedding from text.

        In production, replace with a proper embedding model like:
        - sentence-transformers/all-MiniLM-L6-v2 (384 dims)
        - OpenAI text-embedding-3-small
        - Cohere embed-english-v3.0

        This simple version uses character/word frequency features
        so the app works without an embedding API key for local testing.
        """
        vec = np.zeros(384)

        if not text:
            return vec.tolist()

        words = text.lower().split()
        word_count = len(words)

        # Feature groups (each fills a slice of the 384-dim vector)

        # 1. Basic text stats (0-19)
        vec[0] = min(word_count / 500, 1.0)
        vec[1] = text.count("\n") / max(word_count, 1)
        vec[2] = text.count("→") / max(word_count, 1)
        vec[3] = text.count("#") / max(word_count, 1)
        vec[4] = 1.0 if "```" in text else 0.0
        vec[5] = text.count("?") / max(word_count, 1)
        vec[6] = text.count("!") / max(word_count, 1)
        vec[7] = len([w for w in words if len(w) > 8]) / max(word_count, 1)
        vec[8] = text.count(",") / max(word_count, 1)
        vec[9] = text.count(":") / max(word_count, 1)

        # 2. Character frequency features (20-119)
        for i, char in enumerate("abcdefghijklmnopqrstuvwxyz0123456789"):
            if i + 20 < 120:
                vec[i + 20] = text.lower().count(char) / max(len(text), 1)

        # 3. Word-level features — common tech/LinkedIn words (120-250)
        keyword_groups = [
            ["system", "design", "architecture", "distributed", "scalable"],
            ["java", "python", "code", "function", "class", "method"],
            ["ai", "ml", "model", "llm", "agent", "rag", "embedding"],
            ["career", "interview", "senior", "growth", "team", "lead"],
            ["productivity", "workflow", "efficient", "focus", "habit"],
            ["api", "database", "cache", "queue", "event", "message"],
            ["experience", "learned", "mistake", "lesson", "realized"],
            ["performance", "latency", "throughput", "optimize", "scale"],
        ]
        for gi, group in enumerate(keyword_groups):
            base = 120 + gi * 16
            for wi, keyword in enumerate(group):
                if base + wi < 250:
                    vec[base + wi] = words.count(keyword) / max(word_count, 1)

        # 4. Structural features (250-300)
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        vec[250] = len(paragraphs) / 20
        if paragraphs:
            para_lengths = [len(p.split()) for p in paragraphs]
            vec[251] = np.mean(para_lengths) / 100
            vec[252] = np.std(para_lengths) / 50 if len(para_lengths) > 1 else 0

        # 5. Hash the remaining content for uniqueness (300-383)
        content_hash = hash(text)
        for i in range(300, 384):
            vec[i] = ((content_hash >> (i - 300)) & 1) * 0.1

        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.tolist()

    def add_post(
        self,
        user_id: str,
        content: str,
        category: str,
        post_type: str = "own",
        post_id: Optional[str] = None,
    ) -> str:
        """Add a post to the vector store.

        Args:
            user_id: User identifier
            content: Post text content
            category: Category ID
            post_type: "own" (user's post) or "inspiration" (from others)
            post_id: Optional custom ID
        """
        _id = post_id or f"{user_id}_{datetime.now().timestamp()}"
        vector = self._simple_embedding(content)

        table = self.db.open_table("user_posts")
        table.add(
            [
                {
                    "id": _id,
                    "user_id": user_id,
                    "content": content,
                    "category": category,
                    "post_type": post_type,
                    "vector": vector,
                    "created_at": datetime.now().isoformat(),
                }
            ]
        )
        return _id

    def find_similar_posts(
        self,
        content: str,
        user_id: str,
        post_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 3,
    ) -> list[dict]:
        """Find posts most similar to the given content.

        Args:
            content: Text to find similar posts to
            user_id: Filter by user
            post_type: Optional filter - "own" or "inspiration"
            category: Optional filter by category
            limit: Max results
        """
        vector = self._simple_embedding(content)
        table = self.db.open_table("user_posts")

        query = table.search(vector).limit(limit + 5)  # over-fetch to filter

        results = query.to_list()

        # Filter by user_id and optionally by type/category
        filtered = []
        for r in results:
            if r.get("user_id") != user_id:
                continue
            if r.get("id") == "init":
                continue
            if post_type and r.get("post_type") != post_type:
                continue
            if category and r.get("category") != category:
                continue
            filtered.append(
                {
                    "id": r["id"],
                    "content": r["content"],
                    "category": r["category"],
                    "post_type": r["post_type"],
                    "distance": r.get("_distance", 0),
                }
            )
            if len(filtered) >= limit:
                break

        return filtered

    def get_user_posts(
        self, user_id: str, post_type: Optional[str] = None
    ) -> list[dict]:
        """Get all posts for a user."""
        table = self.db.open_table("user_posts")
        results = table.search().where(f"user_id = '{user_id}'").limit(100).to_list()

        posts = []
        for r in results:
            if r.get("id") == "init":
                continue
            if post_type and r.get("post_type") != post_type:
                continue
            posts.append(
                {
                    "id": r["id"],
                    "content": r["content"],
                    "category": r["category"],
                    "post_type": r["post_type"],
                    "created_at": r.get("created_at", ""),
                }
            )
        return posts

    def compute_style_similarity(self, draft: str, user_id: str) -> float:
        """Compute how well a draft matches the user's writing style.

        Returns a score from 0 to 100.
        """
        similar = self.find_similar_posts(
            content=draft, user_id=user_id, post_type="own", limit=5
        )
        if not similar:
            return 50.0  # No posts to compare against, neutral score

        distances = [s["distance"] for s in similar]
        avg_distance = sum(distances) / len(distances)

        # Convert distance to similarity score (0-100)
        # Lower distance = higher similarity
        score = max(0, min(100, 100 - (avg_distance * 50)))
        return round(score, 1)


# Singleton
vector_store = VectorStore()
