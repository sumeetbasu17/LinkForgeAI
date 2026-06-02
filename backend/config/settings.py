import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4.5")
    LLM_MODEL_LIGHT: str = os.getenv("LLM_MODEL_LIGHT", "anthropic/claude-haiku-4.5")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Search
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./linkedin_posts.db")

    # Vector store
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", "./data/lancedb")

    # LinkedIn
    LINKEDIN_CLIENT_ID: str = os.getenv("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    LINKEDIN_ACCESS_TOKEN: str = os.getenv("LINKEDIN_ACCESS_TOKEN", "")

    # Clerk Auth
    CLERK_SECRET_KEY: str = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    CLERK_JWKS_URL: str = os.getenv("CLERK_JWKS_URL", "")
    # Set to False to disable auth during local development
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"

    # Redis (for Celery scheduler)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Available LLM models via OpenRouter
    AVAILABLE_MODELS: list = [
        {"id": "anthropic/claude-sonnet-4.5", "name": "Claude Sonnet 4.5", "tier": "best", "cost": "$$"},
        {"id": "anthropic/claude-haiku-4.5", "name": "Claude Haiku 4.5", "tier": "fast", "cost": "$"},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "tier": "best", "cost": "$$"},
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "tier": "fast", "cost": "$"},
        {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "tier": "fast", "cost": "$"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B (free)", "tier": "free", "cost": "free"},
    ]

    DEFAULT_CATEGORIES: list = [
        {
            "id": "ai-engineering",
            "label": "AI Engineering & Agents",
            "icon": "🤖",
            "description": "RAG, LangGraph, prompt engineering, AI agents, model comparisons",
        },
        {
            "id": "system-design",
            "label": "System Design (HLD)",
            "icon": "🏗️",
            "description": "CQRS, event sourcing, microservices trade-offs, distributed systems",
        },
        {
            "id": "clean-code",
            "label": "Clean Code & Design Patterns",
            "icon": "☕",
            "description": "SOLID, Java LLD, design patterns, refactoring, code quality",
        },
        {
            "id": "career-growth",
            "label": "Career Growth for SDEs",
            "icon": "📈",
            "description": "SDE to Senior SDE journey, interview insights, team dynamics, growth mindset",
        },
        {
            "id": "productivity",
            "label": "Engineering Productivity",
            "icon": "⚡",
            "description": "Developer workflows, code review habits, deep work, tooling",
        },
        {
            "id": "genai-tools",
            "label": "GenAI Tools & Reviews",
            "icon": "🧪",
            "description": "Hands-on tool reviews, model benchmarks, new framework deep dives",
        },
        {
            "id": "tech-concepts",
            "label": "Tech Deep Dives",
            "icon": "💡",
            "description": "Event-driven architecture, DB internals, networking, concurrency",
        },
    ]

    DEFAULT_POST_FORMATS: list = [
        {"id": "story", "label": "Story-driven", "description": "Personal narrative with a technical lesson"},
        {"id": "listicle", "label": "Listicle", "description": "Numbered tips or actionable insights"},
        {"id": "hot-take", "label": "Hot Take", "description": "Bold opinion backed by experience"},
        {"id": "tutorial", "label": "Mini Tutorial", "description": "Quick how-to with code or steps"},
        {"id": "reflection", "label": "Reflection", "description": "Career lesson or realization from experience"},
        {"id": "trend", "label": "Trend Analysis", "description": "Commentary on what's changing in the industry"},
    ]

    DEFAULT_TONES: list = [
        "Professional",
        "Conversational",
        "Thought-provoking",
        "Inspirational",
        "Technical",
        "Witty",
    ]


settings = Settings()
