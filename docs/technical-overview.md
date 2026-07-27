# LinkedIn Post Generator — technical & product overview

> Recovered from the v0.2.0 documentation PDF. Page markers, running headers
> and the list numbering the PDF extractor mangled have been cleaned up.
> For setup and day-to-day usage see the top-level `README.md`.

---

## Contents

1. Executive Summary
2. What We Built & Why It’s Sellable
3. Architecture & Technology Choices
4. Feature Inventory (Built vs Pending)
5. How Everything Works (End-to-End Flow)
6. DevOps & Deployment
7. Roadmap: Web → Mobile → AWS
8. Go-To-Market: Launch, Pricing & Growth
9. Competitive Analysis & Improvements
10. User Experience Decisions
11. Demo FAQ: Questions & Answers
12. Appendix: File Structure & API Reference

## 1. Executive Summary

LinkedIn Post Generator is an AI-powered content engine that helps senior software
engineers grow their LinkedIn presence by generating high-quality, style-matched posts
2–3 times per week. It combines real-time trend research, personal writing style learning,
and autonomous scheduling to eliminate the friction of consistent content creation.
The Problem
Senior engineers know LinkedIn is valuable for career growth, but most post
inconsistently or not at all. Writing a good post takes 30–60 minutes. Staying consistent
at 3x/week requires 2–3 hours weekly of focused writing — time most engineers don’t
have alongside their day jobs.
The Solution
An AI system that learns your writing voice from your past posts, researches trending
topics in your domain, generates posts that sound like you wrote them, scores them for
engagement potential, and optionally publishes them directly to LinkedIn on a schedule
you set. One-time setup, then it runs autonomously.
Key Metrics
• Target user: Senior SDEs with 5–15+ years experience
• Time saved: 2–3 hours/week per user
• Cost to serve: ~$0.50–$1.00/user/month in LLM API costs
• Revenue target: $19/month subscription × 100 users = $1,900 MRR
• Infrastructure cost: ~$20–$80/month total at 100 users

## 2. What We Built & Why It’s Sellable

### 2.1 Why Engineers Will Pay for This

LinkedIn’s 2026 algorithm (internally called 360Brew) shifted from rewarding viral reach
to prioritizing relevance and depth. The algorithm evaluates topic DNA, dwell time, saves,
and comment quality — not just likes. This means low-effort AI slop gets suppressed, but
well-crafted posts that match an authentic voice get amplified. Our tool specifically
generates high-quality, style-matched content that passes this depth test.
Market Validation
• LinkedIn has 1.5 billion users in 2026 — the #1 B2B platform
• Organic reach is 10% of followers (vs 2% on Instagram)
• 79% of B2B decision-makers ignore cold DMs — inbound content is 8x more effective
• Posting 2–5x/week delivers +1,182 more impressions per post
• Small accounts (1–5K) see 24.5% average growth rate

### 2.2 What Makes This Different from ChatGPT

- Style learning — It reads your past posts and learns YOUR voice, not generic AI writing
Trend research — Tavily searches the web for what’s trending in your niche right now
Quality gate — Vector similarity scoring ensures every post matches your style before
publishing
Full pipeline — Not just drafting. Topic selection, research, draft, quality check, hooks,
scheduling, and LinkedIn publishing
Category-aware tones — Different voice for System Design vs Career Growth posts
Custom rules — “Never write about building in public” is enforced at generation time

## 3. Architecture & Technology Choices

### 3.1 System Architecture

The system has four layers: React frontend, FastAPI backend with REST API, LangGraph
AI agent pipeline, and a dual-database storage layer (SQLite for relational data, LanceDB
for vector embeddings).
Request flow: User clicks Generate → Frontend calls POST /api/generate → FastAPI
validates & loads user preferences → LangGraph pipeline runs 5 nodes (load context →
select topic → research → draft → quality check) → Post saved to SQLite → Response
returned to frontend with engagement scores.

### 3.2 Technology Stack & Rationale

Layer Technology Why This Choice
Frontend React + Vite Single-file component architecture. Vite provides
instant HMR. No framework overhead. PWA-ready
with manifest.json.
Backend API FastAPI (Python) Async-native, auto-generates OpenAPI docs at /
docs, Pydantic validation, easy to learn. Best
Python framework for AI applications.
AI Pipeline LangGraph Stateful multi-step agent with conditional edges.
Allows the quality check to loop back to drafting.
Better than plain LangChain for workflows with
branching logic.
LLM Provider OpenRouter Single API key for 300+ models. Automatic fallback
between providers. User picks model in UI.
Cheaper than direct Anthropic API for multi-model
access.
Vector DB LanceDB Serverless, zero-config, file-based. Runs locally
without Docker or server setup. Stores style
embeddings for similarity search. 10ms query
latency.
Relational DB SQLite Zero-config, single-file database. Perfect for up to
500 concurrent users with WAL mode. Migrates to
PostgreSQL when needed.
Web Search Tavily Purpose-built for AI agents. Returns structured
results. $0.01 per search. 1000 free searches/
month.
Auth Clerk Drop-in authentication. Google/GitHub login. JWT
tokens. User management dashboard. 10,000 free
MAU.
Scheduler APScheduler Runs inside FastAPI process. No Redis needed for
local dev. Checks every 30 min for autonomous
posting. Upgrades to Celery + Redis for production.
Deployment Docker + Railway Dockerfile builds both frontend and backend.
Railway auto-deploys from GitHub. railway.toml
configures health checks and restarts.

### 3.3 Why LangGraph Over Plain LangChain

LangChain LCEL (LangChain Expression Language) runs chains linearly — step 1 → step
2 → step 3. Our pipeline needs a conditional loop: if the quality check scores the draft
below 70/100, it routes BACK to the drafting node with specific feedback. LangGraph
supports this with conditional edges. It also maintains state across all nodes as a typed
dictionary, so each node can read and write to a shared state object.

### 3.4 Why LanceDB Over ChromaDB/FAISS

LanceDB is serverless and file-based — no Docker container, no server process, no
configuration. It stores data in a folder (data/lancedb/) and queries are sub-millisecond.
ChromaDB requires a running server process. FAISS requires manual index
management. For a product that needs to work on a developer’s laptop with zero setup,
LanceDB is the clear choice. It handles up to millions of vectors before needing a hosted
solution.

### 3.5 Database Schema

SQLite (linkedin_posts.db): 4 tables — posts (generated content), user_preferences
(categories, tones, schedule, custom rules, model selection), style_posts (uploaded
articles for style learning), linkedin_tokens (OAuth tokens with auto-refresh).
LanceDB (data/lancedb/): 1 table — user_posts. Each row has user_id, content, category,
post_type (own/inspiration/comment), and a 384-dim vector embedding. Filtered by
user_id + post_type + category at query time. One table serves all users — no per-user
tables needed.

## 4. Feature Inventory

### 4.1 Implemented Features

Feature Status Post Generation (LangGraph
pipeline)
Built Style Learning (upload posts) Built File Upload (.txt, .csv, .json) Built Category-based style upload Built Delete styles (single/category/all) Built Trend Research (Tavily) Built Engagement Prediction Built Hook A/B Testing Built Carousel Generator Built Comment Agent (proactive + reply) Built Content Repurposer Built Hashtag Optimizer Built LinkedIn OAuth + Auto-posting Built Autonomous Scheduling Built Model Selection (OpenRouter) Built Custom Rules Built Tab Persistence (URL hash) Built Form State Persistence Built Page 8
Priority Core Core Core Core Core Core Core Growth Growth Growth Growth Growth Core Core Core Core UX UX Notes
5-node pipeline
with quality loop
Own, inspiration,
comment types
Bulk article import
Tag articles by
category
Full CRUD
Real-time topic
discovery
4-score system
before publish
3 variations with
scores
Post to 8 slides
Draft comments,
not auto-post
4 formats from 1
post
1 broad + 2 niche
+ 1 contextual
Token auto-refresh
APScheduler, 30-
min checks
6 models, user
picks in UI
Injected into LLM
prompt
Survives browser
refresh
Generate tab
survives tab switch
PWA Manifest Clerk Auth Middleware Dark Mode 4.2 Pending Features
Feature Clerk Frontend Integration Stripe Billing Auto-categorize uploads Analytics Dashboard Newsletter Integration Profile Optimizer Content Calendar View Celery + Redis (production) PostgreSQL Migration Proper Embedding Model Voice-to-Post Competitor Tracker Page 9
Built Built Built Status Pending Pending Pending Pending Pending Pending Pending Pending Pending Pending Pending Pending Mobile Scale UX Priority P0 P0 P1 P1 P2 P2 P2 P1 P1 P1 P3 P3 Installable from
mobile browser
AUTH_ENABLED
toggle
Auto-detects
system preference
Notes
Login UI, signup
flow
Free/Pro tier
gating
LLM classifies
articles
Charts, best times,
trends
Convert posts to
newsletter
AI reviews
headline/about
Visual week/month
calendar
Replace
APScheduler at
scale
Replace SQLite at
500+ users
Replace simple
embeddings with
sentence-
transformers
Record audio, AI
transcribes
Monitor niche
voices
PDF Carousel Export Pending P2 Generate actual
PDF slides
React Native (Expo) Pending P3 Native mobile app

## 5. How Everything Works

### 5.1 The LangGraph Pipeline (5 Nodes)

Node 1 — Load Style Context (no LLM): Reads the user’s style profile from SQLite
preferences. Searches LanceDB for the user’s past posts most similar to the requested
topic/category. Also loads inspiration post structures and custom rules. These become
context for the draft node.
Node 2 — Select Topic (LLM light call): If the user didn’t provide a topic, Tavily searches
for trending articles in the selected category. The LLM reads the trends plus the user’s
recent post titles (to avoid repeats) and picks the best topic. ~$0.002 cost.
Node 3 — Research (no LLM): Pure Tavily API calls. Fetches 5–10 articles about the
selected topic, extracts key facts and statistics. This ensures posts have current,
accurate information — not just the LLM’s training data.
Node 4 — Draft Post (LLM heavy call): The main generation step. The LLM receives:
research facts from Tavily, 2–3 similar past posts from LanceDB, the user’s style profile,
their custom rules, the tone/format preferences, and any revision feedback from a
previous quality check. ~$0.03–$0.05 cost.
Node 5 — Quality Check (hybrid): Computes vector cosine similarity between the draft
and the user’s past posts in LanceDB. If the score is below 70/100, an optional light LLM
call provides specific feedback (“add more code examples”). The conditional edge routes
back to Node 4 with this feedback, up to 2 revision loops.

### 5.2 Style Learning

When a user uploads posts, each post is: (1) saved to SQLite style_posts table with
content, category, and type, (2) converted to a 384-dimensional vector embedding, and
(3) stored in LanceDB. During generation, Node 1 does a similarity search: “find the 3
posts from this user that are closest to the current topic.” The retrieved posts become
examples in the LLM prompt — the AI reads them and mimics the patterns.

### 5.3 Autonomous Posting Flow

APScheduler fires every 30 minutes. It checks: (1) is auto_post_enabled true? (2) is today
in preferred_days? (3) is current time within 30 min of preferred_time? (4) has the user
already posted today? If all conditions pass, it picks a random active category, reads the
tone override for that category, runs the full LangGraph pipeline, and calls the LinkedIn
Posts API to publish. The post is saved to SQLite with status “published.”

### 5.4 LinkedIn OAuth Flow

User clicks “Connect LinkedIn” → redirected to LinkedIn authorization page → clicks
Allow → LinkedIn redirects to /api/linkedin/callback with an authorization code →
backend exchanges code for access token (60 days) + refresh token (365 days) → both
tokens saved to SQLite linkedin_tokens table → user redirected back to frontend
Settings tab. Before every API call, the system checks: is the token expiring in < 7 days?
If yes, it automatically uses the refresh token to get a new access token.

## 6. DevOps & Deployment

### 6.1 Local Development

Two terminal tabs: (1) cd backend && python -m uvicorn api.main:app --reload --port 8000
(2) cd frontend && npm run dev. The Vite dev server proxies /api/* requests to the
backend via vite.config.js. Hot module replacement on both sides.

### 6.2 Current Production Path (Railway)

- Push code to GitHub repository
Railway detects Dockerfile, builds multi-stage image (Python backend + React static
build)
9. railway.toml configures health check endpoint (/api/health) and restart policy
10. Environment variables set in Railway dashboard (OPENROUTER_API_KEY,
TAVILY_API_KEY, etc.)
11. Railway provides a public URL with automatic SSL

### 6.3 Dockerfile (Multi-Stage)

Stage 1: Python 3.12 — installs backend dependencies. Stage 2: Node 20 — builds React
frontend into static files. Stage 3: Final image — copies backend code + frontend static
build, serves everything from FastAPI on port 8000.

### 6.4 CloudFlare Tunnel (for testing)

During development, CloudFlare Tunnel exposes your local server to the internet for
testing with real LinkedIn OAuth callbacks, real users, or mobile testing. Command:
cloudflared tunnel --url http://localhost:8000. No deployment needed.

## 7. Roadmap: Web → Mobile → AWS

Phase 1: Web App MVP (Current)
• React + FastAPI on Railway
• SQLite + LanceDB (file-based)
• APScheduler for autonomous posting
• PWA manifest for mobile install from browser
• Target: 0–100 users
Phase 2: Production Scale
• Add Clerk auth + Stripe billing (Pro $19/mo)
• Migrate SQLite → PostgreSQL (managed RDS or Railway Postgres)
• Replace APScheduler → Celery + Redis for reliable scheduling
• Add proper embedding model (sentence-transformers/all-MiniLM-L6-v2)
• Target: 100–500 users
Phase 3: Mobile + AWS
• React Native via Expo (share 80% code with web)
• Push notifications for “Your post was published” and “New comment received”
• Migrate to AWS: ECS Fargate (backend), RDS PostgreSQL, ElastiCache Redis, S3
(media), Lambda (scheduled triggers)
• Target: 500–5000 users
Phase 4: Scale & Differentiation
• Analytics dashboard with charts and trend tracking
• A/B test entire posts (not just hooks)
• Team/agency mode: manage multiple LinkedIn accounts
• API access for power users
• Target: 5000+ users

## 8. Go-To-Market: Launch, Pricing & Growth

### 8.1 Launch Strategy

12. Use the tool yourself for 2–4 weeks. Track engagement growth. Build a case study.
13. Write LinkedIn posts ABOUT the tool: “I built an AI that writes LinkedIn posts in my voice.
Here’s what happened in 30 days.”
14. Launch on Product Hunt and Indie Hackers — free platforms with technical audiences.
15. DM 50 senior engineers who post good content but inconsistently. Offer a free month.
16. Your first 100 users will come from LinkedIn itself — the target audience is already there.

### 8.2 Product Hunt Launch Checklist

• Prepare a 1-minute demo video showing: upload posts → analyze style → generate →
publish
• Write a compelling tagline: “AI that writes LinkedIn posts in YOUR voice, not generic AI
slop”
• Schedule launch for Tuesday 12:01 AM PT (highest traffic day)
• Have 5–10 beta users ready to leave authentic comments on launch day
• Offer lifetime deal or extended trial for early supporters

### 8.3 Pricing

Tier Price Includes
Free $0 3 posts/month, 1 category, manual posting only, no style
learning
Pro $19/mo Unlimited posts, all categories, style learning, auto-scheduling,
hooks, carousel, comments, repurpose
Enterprise $49/mo Everything in Pro + autonomous mode, A/B testing, priority
support, API access, team collaboration

### 8.4 Unit Economics

• LLM cost per post: $0.03–$0.08 (topic selection + draft + quality check)
• Tavily cost per post: $0.01–$0.02 (2–3 searches)
• Total cost per post: ~$0.05–$0.10
• At 12 posts/month per Pro user: ~$0.60–$1.20/user/month
• Subscription revenue: $19/user/month
• Gross margin: ~94–97%

## 9. Competitive Analysis

### 9.1 How We Compare

Feature Our Tool Taplio AuthoredUp ChatGPT
Style learning Yes (vector DB) Basic No No
Trend research Tavily live Limited No Web browse
Quality scoring Vector + LLM No No No
Auto-posting LinkedIn API Yes No No
Hook A/B testing Yes (scored) Templates Templates No
Custom rules Yes No No System prompt
Open source Yes No No No
Price $19/mo $39–$149/mo $19.95/mo $20/mo

### 9.2 Key Improvements to Make

• Add actual embedding model (sentence-transformers) instead of simple feature-based
vectors
• Build analytics dashboard showing which categories/formats/hooks perform best
• Add visual carousel PDF generation (not just text slides)
• Implement auto-categorization when uploading bulk articles
• Add comment style learning (separate from post style)

## 10. User Experience Decisions

### 10.1 Design Principles Applied

• Customer agenda > your agenda — every screen serves a user action, not a feature
showcase
• Every word justifies its presence — labels are short, descriptions minimal
• Color has meaning — green = success/connected, red = error/danger, blue/purple =
accent/primary
• Reduce cognitive load — expandable sections, progressive disclosure, sensible defaults
• Submit buttons never disable — they show loading state but remain visually present
• Dark mode — auto-detects system preference via CSS variables

### 10.2 UX Decisions Made

• Tab state persists in URL hash (#settings, #content) — refresh stays on same tab
• Generate form state lifts to parent — switching tabs doesn’t lose your selections
• LinkedIn publish only updates status AFTER confirmed API success
• Toast notifications auto-dismiss in 4 seconds, appear bottom-right
• Style upload shows counts by type (My Posts / Inspiration / Comments) as prominent
cards
• Model selector shows tier badges (best/fast/free) with cost indicator
• Autonomous mode shows clear ON/OFF messaging about what happens in each state

## 11. Demo FAQ: Questions & Answers

Q: How is this different from just using ChatGPT?
A: ChatGPT doesn’t know your writing style, doesn’t research what’s trending in your
niche right now, doesn’t score posts for engagement potential, can’t publish to LinkedIn,
and can’t run autonomously on a schedule. Every time you use ChatGPT, you start from
scratch. Our tool maintains your style profile and improves over time.
Q: Will LinkedIn penalize AI-generated content?
A: LinkedIn’s algorithm penalizes generic, low-quality content regardless of how it was
written. It rewards depth, relevance, and authentic voice. Because our tool matches your
personal writing style and uses real-time research, the output passes LinkedIn’s quality
filters. The quality gate specifically ensures posts don’t sound like generic AI.
Q: How many posts do I need to upload for style learning?
A: Minimum 2, but 5–10 gives much better results. The more posts the AI reads, the more
accurately it captures your sentence structure, emoji usage, hook style, and technical
depth. Upload your best-performing posts for the strongest style match.
Q: What if I don’t like the generated post?
A: Click Regenerate. Each generation produces a different post even with the same topic.
You can also edit the content directly in the Content tab before publishing. The tool
generates drafts, not final posts — you always have the final say.
Q: How does autonomous mode work without my input?
A: You configure it once: pick active categories, set tones per category, choose days/
times, add custom rules, and turn it on. The AI picks topics from trending research,
applies your style, generates the post, scores it, and publishes. All posts are saved and
visible in the Content tab for review.
Q: Can I use my own OpenRouter/Tavily API keys?
A: Yes, but for the paid product, we recommend baking the API cost into the
subscription. Users don’t need their own keys — it just works. Power users can override
with their own keys in an advanced settings section.
Q: What about data privacy?
A: Your posts, style profile, and preferences are stored in your own database. With Clerk
auth, each user’s data is isolated by user_id. We don’t share content between users. The
LLM processes your content but OpenRouter doesn’t train on API inputs.
Q: Why not just use Taplio or similar tools?
A: Taplio starts at $39/month and doesn’t learn your specific writing voice. It uses
templates and scheduling. Our tool uses a full AI pipeline with style matching, trend
research, quality scoring, and engagement prediction — at $19/month.

## 12. Appendix: File Structure & API Reference

### 12.1 Project Structure (32 code files)

backend/agents/state.py — TypedDict pipeline state
backend/agents/nodes.py — 5 node functions
backend/agents/graph.py — LangGraph pipeline definition
backend/api/main.py — FastAPI routes (~650 lines)
backend/api/auth.py — Clerk JWT middleware
backend/api/schemas.py — Pydantic request/response models
backend/config/settings.py — Environment config + defaults
backend/db/database.py — SQLite operations
backend/db/vector_store.py — LanceDB operations
backend/services/llm.py — OpenRouter wrapper
backend/services/research.py — Tavily wrapper
backend/services/style_analyzer.py — Style profile extraction
backend/services/linkedin_api.py — OAuth + posting
backend/services/carousel.py — Carousel slide generation
backend/services/hook_tester.py — Hook A/B testing
backend/services/comment_agent.py — Comment drafting
backend/services/repurposer.py — Content format conversion
backend/services/hashtag_optimizer.py — Hashtag selection
backend/services/engagement_predictor.py — Scoring + analytics
backend/services/scheduler.py — APScheduler for auto-posting
frontend/src/App.jsx — All 8 tabs (~430 lines)
frontend/src/utils/api.js — API client (all 25+ endpoints)

### 12.2 API Endpoints (25 total)

Method Path Purpose
GET /api/health Health check + version
GET /api/test-llm Test OpenRouter connection
GET /api/config Categories, formats, tones, models
POST /api/generate Generate post via LangGraph pipeline
GET /api/posts List posts (filterable by status/category)
GET /api/posts/{id} Get single post
PUT /api/posts/{id} Update post content/status/schedule
DELETE /api/posts/{id} Delete post
POST /api/style/posts Add style post (own/inspiration/comment)
GET /api/style/posts List style posts (filterable)
GET /api/style/counts Counts by category and type
DELETE /api/style/posts/{id} Delete single style post
DELETE /api/style/posts Bulk delete by category/type/all
POST /api/style/upload Upload file with multiple articles
POST /api/style/analyze Trigger full style analysis
GET /api/style/profile Get current style profile
GET /api/models List available LLM models
PUT /api/models/select Set preferred model
GET/PUT /api/rules Get/set custom generation rules
GET/PUT /api/preferences Get/set user preferences
POST /api/carousel Generate carousel slides
POST /api/hooks Generate hook variations
POST /api/comments/* Draft replies and proactive comments
POST /api/repurpose Repurpose into 4 formats
GET /api/linkedin/auth Start LinkedIn OAuth flow
GET /api/linkedin/callback Handle OAuth callback
GET /api/linkedin/status Check connection + token health
POST /api/linkedin/post Publish to LinkedIn
