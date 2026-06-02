"""
Engagement Predictor & Analytics Tracker.
Scores posts before publishing and tracks what works over time.

LinkedIn 2026 "Depth Score" factors:
- Dwell time (people staying 15+ seconds)
- Saves (highest-weight signal)
- Shares with context
- Comment quality (replies, not just "great post")
- Likes are de-emphasized
"""

import json
import re
from db.database import database
from services.llm import llm_service


class EngagementPredictor:
    """Predicts engagement potential and tracks patterns."""

    async def predict_engagement(self, post_content: str, category: str = "", format: str = "") -> dict:
        """Score a post's engagement potential before publishing.

        Returns:
        {
            "overall_score": 0-100,
            "dwell_time_score": 0-100 (will people read the whole thing?),
            "save_potential": 0-100 (is this reference-worthy?),
            "comment_potential": 0-100 (does it invite discussion?),
            "share_potential": 0-100 (would someone share this?),
            "improvements": ["specific suggestion 1", "suggestion 2"],
            "predicted_reach": "low/medium/high/viral"
        }
        """
        system_prompt = """You are a LinkedIn engagement analyst.
Score posts based on LinkedIn's 2026 algorithm priorities:

SCORING FACTORS:
1. Dwell time: Does the post reward reading? Long enough to be valuable, formatted for easy scanning?
2. Save potential: Is this something engineers would bookmark? Frameworks, code, checklists score high.
3. Comment potential: Does it ask a question? Present a debatable take? Invite stories?
4. Share potential: Would someone share this with their team? "You need to read this" factor.

ANTI-PATTERNS (reduce score):
- External links (LinkedIn suppresses these)
- Too many hashtags (>5 is spammy)
- Generic advice without specifics
- No hook in first 2 lines
- No CTA at the end
- Wall of text without formatting"""

        user_prompt = f"""Score this LinkedIn post:

{post_content}

Category: {category}
Format: {format}

Return JSON:
{{
  "overall_score": 0-100,
  "dwell_time_score": 0-100,
  "save_potential": 0-100,
  "comment_potential": 0-100,
  "share_potential": 0-100,
  "improvements": ["improvement 1", "improvement 2", "improvement 3"],
  "predicted_reach": "low/medium/high/viral",
  "hook_rating": "weak/decent/strong/excellent"
}}"""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=True)
            return result
        except Exception:
            # Basic heuristic scoring
            score = 50
            word_count = len(post_content.split())
            has_question = "?" in post_content
            has_code = "```" in post_content
            has_numbers = bool(re.search(r'\d+%|\d+x|\d+K', post_content))
            has_hashtags = len(re.findall(r'#\w+', post_content))
            line_breaks = post_content.count("\n\n")

            if 100 <= word_count <= 250: score += 10
            if has_question: score += 10
            if has_code: score += 5
            if has_numbers: score += 10
            if 2 <= has_hashtags <= 4: score += 5
            if line_breaks >= 3: score += 5
            if "http" in post_content: score -= 15

            return {
                "overall_score": min(score, 100),
                "dwell_time_score": 60,
                "save_potential": 70 if has_code or has_numbers else 40,
                "comment_potential": 70 if has_question else 35,
                "share_potential": 50,
                "improvements": ["Add a question at the end", "Include specific numbers"],
                "predicted_reach": "medium",
                "hook_rating": "decent",
            }

    def get_content_analytics(self, user_id: str = "default") -> dict:
        """Analyze what's working based on past post performance.

        Returns insights on best categories, formats, posting times, etc.
        """
        posts = database.list_posts(user_id=user_id, status="published", limit=50)

        if not posts:
            return {"message": "No published posts yet. Publish some posts to see analytics.", "total_posts": 0}

        total_likes = sum(p.get("likes", 0) for p in posts)
        total_comments = sum(p.get("comments", 0) for p in posts)
        total_impressions = sum(p.get("impressions", 0) for p in posts)

        # Category performance
        cat_stats = {}
        for p in posts:
            cat = p.get("category", "unknown")
            if cat not in cat_stats:
                cat_stats[cat] = {"posts": 0, "likes": 0, "comments": 0, "impressions": 0}
            cat_stats[cat]["posts"] += 1
            cat_stats[cat]["likes"] += p.get("likes", 0)
            cat_stats[cat]["comments"] += p.get("comments", 0)
            cat_stats[cat]["impressions"] += p.get("impressions", 0)

        # Sort by engagement rate
        for cat in cat_stats:
            imp = cat_stats[cat]["impressions"] or 1
            cat_stats[cat]["engagement_rate"] = round(
                (cat_stats[cat]["likes"] + cat_stats[cat]["comments"]) / imp * 100, 2
            )

        best_cat = max(cat_stats, key=lambda c: cat_stats[c].get("engagement_rate", 0)) if cat_stats else None

        # Format performance
        format_stats = {}
        for p in posts:
            fmt = p.get("format", "unknown")
            if fmt not in format_stats:
                format_stats[fmt] = {"posts": 0, "total_engagement": 0}
            format_stats[fmt]["posts"] += 1
            format_stats[fmt]["total_engagement"] += p.get("likes", 0) + p.get("comments", 0)

        return {
            "total_posts": len(posts),
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_impressions": total_impressions,
            "avg_engagement_rate": round((total_likes + total_comments) / max(total_impressions, 1) * 100, 2),
            "category_performance": cat_stats,
            "format_performance": format_stats,
            "best_category": best_cat,
            "recommendations": [],
        }


engagement_predictor = EngagementPredictor()
