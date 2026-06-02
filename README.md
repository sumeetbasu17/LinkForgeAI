# LinkedIn Post Generator

AI-powered LinkedIn content engine for senior SDEs. Generates high-quality, style-matched posts using LangGraph agents, vector similarity, and real-time trend research.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  Dashboard · Editor · Calendar · Style · Analytics   │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                       │
│  /generate · /posts · /style · /schedule · /auth     │
└──────┬───────────┬───────────┬──────────────────────┘
       │           │           │
┌──────▼──┐  ┌─────▼────┐  ┌──▼──────────┐
│LangGraph│  │ LanceDB  │  │ PostgreSQL  │
│  Agent  │  │ (vectors)│  │ (data)      │
│Pipeline │  │          │  │             │
└──┬───┬──┘  └──────────┘  └─────────────┘
   │   │
┌──▼┐ ┌▼────────┐
│LLM│ │ Tavily  │
│API│ │ Search  │
└───┘ └─────────┘
```

## Quick Start (Local Testing)

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys (see `.env.example`)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Add your API keys
python -m uvicorn api.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # Opens on http://localhost:5173
```

### API Keys Needed
- `OPENROUTER_API_KEY` — LLM calls (get from openrouter.ai)
- `TAVILY_API_KEY` — Web search (get from tavily.com)
- Both have free tiers sufficient for testing.

## Project Structure

```
backend/
├── agents/
│   ├── graph.py          # LangGraph pipeline definition
│   ├── nodes.py          # Individual node functions
│   └── state.py          # Agent state schema
├── api/
│   ├── main.py           # FastAPI app + routes
│   └── schemas.py        # Pydantic request/response models
├── db/
│   ├── vector_store.py   # LanceDB operations (style embeddings)
│   └── database.py       # SQLite/PostgreSQL (posts, users, schedules)
├── services/
│   ├── llm.py            # OpenRouter LLM wrapper
│   ├── research.py       # Tavily search wrapper
│   └── style_analyzer.py # Style profile extraction
├── config/
│   └── settings.py       # Environment config
└── requirements.txt

frontend/
├── src/
│   ├── components/       # Reusable UI components
│   ├── pages/            # Tab views
│   ├── hooks/            # Custom React hooks
│   └── utils/            # API client, helpers
└── package.json
```

## How It Works

1. **You provide**: Past posts (learns your voice), categories, tone preferences
2. **AI researches**: Tavily fetches trending topics in your categories
3. **AI drafts**: LLM generates post using your style profile + fresh research
4. **Quality gate**: Vector similarity scores style match; refines if needed
5. **You review or auto-publish**: Manual approval or autonomous scheduling
```
