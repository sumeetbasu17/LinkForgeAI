"""
Comment Engagement Agent.
Generates thoughtful reply drafts for comments on your posts.
Replying within 1 hour boosts algorithm distribution significantly.

Also generates proactive comments for other people's posts
(the "comment-first" strategy for network growth).
"""

from services.llm import llm_service


class CommentAgent:
    """AI-powered comment drafting for engagement."""

    async def draft_reply(
        self,
        original_post: str,
        comment_text: str,
        commenter_name: str = "",
        tone: str = "Conversational",
    ) -> dict:
        """Draft a reply to a comment on your post.

        Returns {"reply": str, "strategy": str}
        strategy explains why this reply works.
        """
        system_prompt = f"""You draft LinkedIn comment replies for a Senior SDE.
Tone: {tone}

RULES:
1. Address the commenter by name if provided
2. Add value — don't just say "thanks!"
3. Ask a follow-up question to keep the conversation going
4. Keep it under 50 words
5. Be genuine, not salesy
6. If they shared an experience, acknowledge it specifically"""

        user_prompt = f"""Your post: {original_post[:200]}...

Comment from {commenter_name or 'someone'}: "{comment_text}"

Return JSON: {{"reply": "your reply text", "strategy": "why this reply works (1 sentence)"}}"""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=True)
            return result
        except Exception:
            return {
                "reply": f"Great point{', ' + commenter_name if commenter_name else ''}! What's been your experience with this?",
                "strategy": "Fallback: acknowledges and asks follow-up",
            }

    async def draft_proactive_comment(
        self,
        target_post: str,
        your_expertise: str = "Senior SDE with 12+ years in backend engineering",
        tone: str = "Conversational",
    ) -> dict:
        """Draft a thoughtful comment on someone else's post.

        This is the "comment-first" strategy: engage 30-50 times daily
        on others' posts to build visibility before they see your content.

        Returns {"comment": str, "strategy": str}
        """
        system_prompt = f"""You draft LinkedIn comments that add genuine value.
You are: {your_expertise}
Tone: {tone}

RULES:
1. Add a unique insight from YOUR experience — don't just agree
2. Share a specific example, number, or contrarian angle
3. Ask a thoughtful question that shows you read carefully
4. Keep it 30-60 words
5. NEVER pitch yourself or your product
6. Start with the insight, not "Great post!"
7. Comments should teach or challenge ideas respectfully"""

        user_prompt = f"""Post you want to comment on:
"{target_post[:500]}"

Return JSON: {{"comment": "your comment text", "strategy": "why this comment adds value (1 sentence)"}}"""

        try:
            result = await llm_service.call_structured(system_prompt, user_prompt, light=True)
            return result
        except Exception:
            return {
                "comment": "Interesting perspective. In my experience building distributed systems, the trade-off looks slightly different — what scale are you seeing this at?",
                "strategy": "Fallback: adds experience-based insight with question",
            }

    async def batch_draft_replies(
        self,
        original_post: str,
        comments: list[dict],
        tone: str = "Conversational",
    ) -> list[dict]:
        """Draft replies for multiple comments at once.

        comments: [{"name": str, "text": str}, ...]
        Returns: [{"name": str, "comment": str, "reply": str}, ...]
        """
        results = []
        for comment in comments[:10]:  # Cap at 10 to manage LLM costs
            reply = await self.draft_reply(
                original_post=original_post,
                comment_text=comment.get("text", ""),
                commenter_name=comment.get("name", ""),
                tone=tone,
            )
            results.append({
                "name": comment.get("name", ""),
                "comment": comment.get("text", ""),
                "reply": reply.get("reply", ""),
                "strategy": reply.get("strategy", ""),
            })
        return results


comment_agent = CommentAgent()
