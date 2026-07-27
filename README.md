# LinkedIn Post Generator

AI-powered LinkedIn content engine for senior SDEs. Learns your writing voice from your
past posts, researches what's current, drafts in your style, scores the result, and can
publish on a schedule — with a matching image when the post actually warrants one.

Product and go-to-market detail lives in [`docs/technical-overview.md`](docs/technical-overview.md).

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  Generate · Content · Style · Images · Settings      │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                       │
│  /generate · /posts · /style · /images · /linkedin   │
└──────┬───────────┬───────────┬──────────┬───────────┘
       │           │           │          │
┌──────▼──┐  ┌─────▼────┐  ┌──▼──────┐  ┌▼──────────┐
│LangGraph│  │ LanceDB  │  │ SQLite  │  │ Chromium  │
│  Agent  │  │ (vectors)│  │ (data)  │  │ (images)  │
└──┬───┬──┘  └──────────┘  └─────────┘  └───────────┘
   │   │
┌──▼┐ ┌▼────────┐
│LLM│ │ Tavily  │
│API│ │ Search  │
└───┘ └─────────┘
```

## Quick start

### Prerequisites

- Python 3.11+, Node.js 18+
- API keys (see `.env.example`)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium   # required for post images
cp .env.example .env                      # add your keys
uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Check `GET /api/test-llm` first if generation misbehaves — it
reports exactly which model and key it tried.

## The generation pipeline

```
load_style_context → select_topic → research → draft_post → quality_check
                                          ↑                       │
                                          └──── (if revise) ──────┘
                                                                  │
                                                       decide_visual → END
```

`quality_check` scores the draft against your style vectors and sends it back for revision
below 70, up to `max_revisions`. `decide_visual` then judges the finished post and decides
whether it deserves an image. The image is not rendered during generation — the decision
comes back on the response so you can accept, change, or drop it.

## Style learning

Upload your past posts under **Style → My posts**. Uploads are parsed by
`services/article_parser.py`, which is deliberately careful about a few things:

- **PDFs are read as one continuous document.** Articles routinely cross a page boundary;
  splitting page-first fragments them.
- **Paragraph breaks are rebuilt from line geometry.** Extractors emit one line per
  *visual* line, so a soft wrap and a real paragraph break look identical in plain text.
  Since `style_analyzer` measures your paragraph rhythm, getting this wrong corrupts the
  style profile. Wrap gaps (~2pt) and paragraph gaps (~17pt) are told apart by line height.
- **Article headers are matched typo-tolerantly.** Real exports contain `Artcle 11`,
  `Artcile 13`, `Arctle 21`. Guards stop `Option 1:` inside a post from splitting it.
- **Ligatures are normalised** (`beneﬁts` → `benefits`) so embeddings see real words.
- **Post URLs are stitched back together** when the PDF broke them across lines or pages.

Splitting falls back through `Article N :` headers → `---` separators → post URLs → blank
lines → single document, and the upload response reports which method was used plus any
gaps in the article numbering.

### Chunking

**One article is one chunk. Posts are not split further.** Style is a whole-document
property — hook, build, payoff, CTA — and a retrieved half-post teaches the generator half
an arc. LinkedIn posts run 100–400 words, comfortably inside any embedding window, so
there is no technical reason to split them either.

### Categorization

Uploads with **Auto-detect** classify every article, in batches of 10 run 4-concurrent.
Batches answer with an index-keyed map rather than an array, so a dropped entry cannot
shift every later article onto the wrong category. Anything a batch misses is retried
individually, then falls back to `FALLBACK_CATEGORY`. Nothing is left blank.

If an earlier import left posts uncategorized, **Style → Auto-categorize N uncategorized**
backfills them without re-uploading. Fragments from a bad import can't be repaired this
way — delete and re-import those.

### Writing constraints

`draft_post` forbids inventing the author's experience — no fabricated incidents, metrics,
employers, or timelines. The only personal experience it may reference is what appears in
your uploaded posts; everything else is framed as observation or analysis. It also emits no
markdown, since LinkedIn renders `**bold**` as literal asterisks.

Add your own constraints under **Settings → Custom rules**. A tuned starting point is in
[`docs/custom-rules.md`](docs/custom-rules.md).

## Post images

Images are **rendered from HTML templates**, not produced by an image model. Every
archetype is text in a layout — handles, code, and diagram labels have to be exactly
right, which is what diffusion models are worst at. Templates give pixel-accurate text,
your real avatar, and identical output every run at no per-image cost.

| Archetype | What it is |
|---|---|
| `social-card` | Avatar, name, handle, then a technical question |
| `interview-card` | Adds a series badge, coloured title, highlights, CTA footer |
| `code-card` | Syntax-highlighted snippet in a window frame; supports before/after |
| `diagram` | Architecture or flow, drawn from LLM-written Mermaid |

### When an image is generated

Most posts don't get one. A weak image makes a thoughtful post look like filler, so the
default is no. `services/visual_agent.py` says yes only when the post contains something a
reader couldn't just restate: real code, a named system with a direction of travel, or a
technical question with a correct answer the post then supplies.

The distinction that does the work is **technical question vs conversational question**:

- *"What happens to a payment that's halfway done when the service crashes?"* — has a
  correct answer. Gets a card.
- *"Who was the manager that built a great culture around you?"* — invites the reader to
  share. The image would only repeat the post's opinion. No card.

Because models tend to say yes to anything ending in a question mark, a deterministic veto
backs up the judgement: a `code-card` is refused when the post contains no code, a
`diagram` when there's no flow, and the person-shaped cards when the post poses no question
or has no technical substance behind it.

### Inspiration styles

Upload reference images under **Images → Inspiration styles**. Each one is read *once* by a
vision model, which extracts a **style preset** — palette, accent, emphasis treatment,
layout archetype, footer text — stored as JSON. Generation reads the preset, never the
image again.

Nothing is trained. You cannot train a model on a handful of images; you can describe one
precisely and reuse the description forever. Vision output is treated as untrusted: colours
are hex-validated, gradients allowlisted, enums coerced, strings truncated.

### Identity and handles

Set your display name, headline, and photo under **Images → Card identity**, and keep a pool
of handles that rotate round-robin (least-used first, ties broken by oldest use) so the same
handle never repeats while others are unused.

The verified badge defaults to **off** on purpose. Next to your real name and photo on a
joke handle, a checkmark reads as a screenshot of a verified account that doesn't exist.

## Settings and the Generate tab

One rule governs both: **Settings are the defaults, an explicit choice wins.**

- **Autonomous mode** has nobody at the keyboard, so it runs entirely on Settings.
- **The Generate tab** starts from Settings but sends whatever you picked, and that is what
  the post is written in. Nothing is silently overridden.

| Setting | Default | What reads it |
|---|---|---|
| Active categories | *(none)* | **Autonomous mode only.** One is picked at random per run. Empty means autonomous posting does nothing. The Generate tab always offers all categories. |
| Tone per category | *(none)* | Autonomous mode. In the Generate tab it *prefills* the tone when you pick that category — change it and your choice is used. |
| Default tone / format | Conversational / story | Both. Autonomous uses them directly; the Generate tab opens on them. |
| Days | Tue, Thu, Sat | Autonomous mode. These set your cadence. |
| Time | 9:00 AM | Autonomous mode. A post fires from this time up to 4 hours later. |
| Weekly cap | 3 | Autonomous mode. A hard ceiling on posts per week, counted Monday–Sunday. |
| Autonomous mode | off | Master switch for the scheduler. |
| Custom rules | *(empty)* | Both manual and autonomous generation. |
| LLM model | Claude Sonnet 4.5 | Heavy calls. Light calls (classification, scoring) always use Haiku. |

### Days vs weekly cap

They do different jobs. **Days decide when** a post goes out; **the cap decides how many
at most.** Select five days with a cap of three and you get posts on the first three
eligible days, then nothing until Monday. The cap is a safety rail against a misconfigured
schedule quietly posting to your LinkedIn every day.

### Autonomous mode

A scheduler tick runs every 10 minutes and generates a post when **all** of these hold:

1. Autonomous mode is on
2. At least one active category is selected
3. Today is a selected day
4. The weekly cap has room
5. Nothing has been published today
6. The current time is at or after your target time, and within the 4-hour catch-up window

It then picks a random active category, applies that category's tone override, generates,
and publishes to LinkedIn. If LinkedIn isn't connected or publishing fails, the post is
saved with status `scheduled` rather than lost.

**The catch-up window matters.** A laptop that slept through 9:00 AM, or a server that
restarted, shouldn't silently cost you the day's post. Anything from the target time until
four hours later still counts. Past that, the day is skipped.

### Why isn't it posting?

`GET /api/scheduler/status` answers this directly, and the same panel appears under
**Settings → Autonomous mode**. It reports whether it would post right now and exactly why
not — wrong day, too early, cap reached, already posted, no categories — plus the posting
window, the week's count against the cap, whether the background job is alive, and what the
last tick decided.

It calls the same `evaluate()` the scheduler uses, so the diagnostic can't drift from the
real behaviour.

**A note on APScheduler:** the job sets `misfire_grace_time` explicitly. The library default
is one second, so any run it is more than a second late for is dropped silently — which a
reloading dev server or a sleeping laptop triggers constantly, skipping every tick with only
a `Run time of job ... was missed by` line to show for it.

### Generate tab

Opens on your `default_format` and `default_tone` from Settings. Picking a category
prefills that category's tone override, with a note saying where the value came from —
click any other tone and yours is used instead.

The API follows the same rule: send `tone` or `format` and they win; leave them blank and
the request falls back to the category's tone override, then your defaults.

## Project structure

```
backend/
  agents/          LangGraph state, nodes, graph
  api/             FastAPI routes, schemas, auth
  config/          Settings and category definitions
  db/              SQLite + LanceDB
  services/
    article_parser.py     Upload parsing and article splitting
    auto_categorizer.py   Batched classification
    style_analyzer.py     Style profile extraction
    visual_agent.py       Image decision + card content
    image_templates.py    HTML for each archetype
    image_renderer.py     Playwright → PNG
    image_style.py        Vision analysis of inspiration images
    linkedin_api.py       OAuth and publishing
    scheduler.py          Autonomous posting
frontend/src/      React app, all tabs in App.jsx
docs/              Product and technical overview
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required. All LLM calls. |
| `TAVILY_API_KEY` | — | Trend research. |
| `LLM_MODEL` | `anthropic/claude-sonnet-4.5` | Drafting. |
| `LLM_MODEL_LIGHT` | `anthropic/claude-haiku-4.5` | Classification, scoring, decisions. |
| `VISION_MODEL` | `anthropic/claude-sonnet-4.5` | Inspiration image analysis. |
| `FALLBACK_CATEGORY` | `career-growth` | Used only when classification is unreachable. |
| `MEDIA_DIR` | `./data/media` | Generated images, avatars, references. |
| `AUTH_ENABLED` | `false` | Clerk JWT verification. |

## Deployment notes

- **Fonts matter.** The Dockerfile installs `fonts-noto-color-emoji` and friends. Without
  them Chromium draws empty boxes where text and emoji should be.
- **Chromium is required** for image rendering: `playwright install --with-deps chromium`.
  Without it the image endpoints return 503 with the install command; everything else works.
- **Mermaid loads from a CDN** at render time. To run fully offline, vendor
  `mermaid.min.js` and point `MERMAID_CDN` in `image_templates.py` at the local copy.

## Known gaps

- `linkedin_api.py` publishes text only — generated images are not attached to auto-posts yet.
- The scheduler handles the `default` user only.
- Comparison-table archetype from the inspiration set isn't built yet.
