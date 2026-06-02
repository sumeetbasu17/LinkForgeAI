"""
LangGraph pipeline definition.
Connects all nodes into the post generation agent graph.

Flow:
  load_style_context → select_topic → research → draft_post → quality_check
                                                       ↑                |
                                                       └── (if revise) ←┘
"""

from langgraph.graph import StateGraph, END

from agents.state import PostGenerationState, make_initial_state
from agents.nodes import (
    load_style_context,
    select_topic,
    research,
    draft_post,
    quality_check,
    should_revise,
)


def create_post_generation_graph() -> StateGraph:
    """Build and compile the LangGraph agent for post generation."""

    graph = StateGraph(PostGenerationState)

    # Add nodes
    graph.add_node("load_style_context", load_style_context)
    graph.add_node("select_topic", select_topic)
    graph.add_node("research", research)
    graph.add_node("draft_post", draft_post)
    graph.add_node("quality_check", quality_check)

    # Define edges (the flow)
    graph.set_entry_point("load_style_context")
    graph.add_edge("load_style_context", "select_topic")
    graph.add_edge("select_topic", "research")
    graph.add_edge("research", "draft_post")
    graph.add_edge("draft_post", "quality_check")

    # Conditional edge: quality_check decides whether to revise or finalize
    graph.add_conditional_edges(
        "quality_check",
        should_revise,
        {
            "revise": "draft_post",  # Go back to draft with feedback
            "finalize": END,  # Done — post is ready
        },
    )

    return graph.compile()


# Compiled graph — ready to invoke
post_generation_agent = create_post_generation_graph()


async def generate_post(
    user_id: str = "default",
    category: str = "",
    topic: str = "",
    format: str = "story",
    tone: str = "Conversational",
) -> dict:
    """Main entry point for generating a LinkedIn post.

    Args:
        user_id: User identifier
        category: Category ID (e.g., "ai-engineering")
        topic: Optional specific topic (AI will pick one if empty)
        format: Post format (story, listicle, hot-take, etc.)
        tone: Writing tone (Professional, Conversational, etc.)

    Returns:
        dict with final_post, final_title, style_score, status, etc.
    """
    initial_state = make_initial_state(
        user_id=user_id,
        category=category,
        topic=topic,
        format=format,
        tone=tone,
    )

    # Run the agent
    final_state = await post_generation_agent.ainvoke(initial_state)

    return dict(final_state)
