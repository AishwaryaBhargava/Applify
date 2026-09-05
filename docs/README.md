# Applify
### Your Job Application Co-Pilot

Applify is a dedicated AI workspace for job applications. Each chat is one job opening. Your profile is always in context. Analysis, tailored resumes, cover letters, and application answers are all on demand — organized, tracked, and never buried in a general-purpose chat.

---

## Live URLs

| | URL |
|---|---|
| Frontend | TBD — Vercel |
| Backend | TBD — Render |

---

## What it does

- **Profile** — Upload your resume and Applify parses it into a structured, persistent profile. Enrich it manually at any time.
- **Job Chats** — Each chat is one job opening. Paste a JD, choose your analysis depth, and get a fit analysis grounded in your profile.
- **Analysis** — Quick snapshot (fit score, top strengths, top gaps, verdict) or detailed breakdown (skill-by-skill, gap reasoning, suggestions).
- **Outputs** — Ask for a tailored resume, cover letter, or help with an application question. Generated on demand, never auto-pushed.
- **Tracker** — Auto-created when you start a chat. Track status, analysis type, and whether you used an AI-tailored resume or sent it unaltered.

---

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Backend | Python FastAPI + Uvicorn |
| Database | Supabase (Postgres) |
| Auth | Supabase Auth (email + Google) |
| AI — Fast | Groq (openai/gpt-oss-120b) |
| AI — Quality | Azure AI Foundry (GPT-4o) |
| Frontend Deploy | Vercel |
| Backend Deploy | Render |

---

## Local Setup

### Prerequisites

- Node.js v18+
- Python 3.11+
- A Supabase project
- A Groq API key
- An Azure AI Foundry resource with GPT-4o deployed

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/applify.git
cd applify
```

### 2. Backend setup

```bash
cd backend
py -3.11 -m venv venv          # macOS/Linux: python3.11 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with your credentials (see Environment Variables below).

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000. Confirm with:

```bash
curl http://localhost:8000/health
# { "status": "ok", "db": "ok", "version": "5ce180c" }
```

`status` is liveness and stays `ok` for as long as the process is answering.
`db` is a `SELECT 1` with a two-second ceiling, so an unreachable database
reads as `"db": "error"` on a 200 rather than as a failed request — Render must
not recycle a healthy instance over a database blip. `version` is the running
build's short git sha, or `dev` when there is no git metadata.

Python 3.11 is not incidental: it is the version Render runs, pinned in
`backend/.python-version` and in `render.yaml` as `PYTHON_VERSION`, so the
local environment matches the deployed one.

### 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
```

Fill in `.env` with your credentials (see Environment Variables below).

```bash
npm run dev
```

Frontend runs at http://localhost:5173.

---

## Environment Variables

### Backend (`backend/.env`)

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-azure-key>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_GPT4O_DEPLOYMENT=gpt-4o
GROQ_API_KEY=<your-groq-key>
GROQ_MODEL=openai/gpt-oss-120b
LLM_FALLBACK_ENABLED=true
LLM_PREFER_AZURE_FOR_CHAT=false
SUPABASE_DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<dbname>
SUPABASE_JWT_SECRET=<your-supabase-jwt-secret>
SUPABASE_URL=https://<your-project>.supabase.co
ALLOWED_ORIGINS=http://localhost:5173
LOG_LEVEL=INFO
```

`ALLOWED_ORIGINS` is compared against the browser's `Origin` header by exact
string, so a trailing slash or a missing scheme would match nothing and block
the frontend with no server-side error to read. Both are corrected at startup
and the correction is logged.

### Frontend (`frontend/.env`)

```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<your-project>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

---

## Supabase Setup

### Local development (default)

The whole stack -- Postgres, Auth, Studio, mail catcher -- runs in Docker via the
Supabase CLI. Requires Docker Desktop.

```bash
npx supabase start   # first run pulls ~10 images, several minutes
npx supabase stop    # data is kept; add --no-backup to wipe the database
```

| Service | URL |
| --- | --- |
| API gateway | http://127.0.0.1:54321 |
| Postgres | postgresql://postgres:postgres@127.0.0.1:54322/postgres |
| Studio | http://127.0.0.1:54323 |
| Mailpit (sent emails) | http://127.0.0.1:54324 |

The three env values, already filled into `.env.example` (they are the CLI's
public demo credentials, not secrets):

```
SUPABASE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
SUPABASE_URL=http://127.0.0.1:54321
VITE_SUPABASE_ANON_KEY=<the ANON_KEY printed by supabase start>
```

`supabase start` also prints `SUPABASE_JWT_SECRET` (the legacy HS256 secret) and
a `sb_publishable_...` key -- either that or the JWT `ANON_KEY` works as
`VITE_SUPABASE_ANON_KEY`. Local auth signs tokens with ES256 signing keys, so
the backend's JWKS path is what actually verifies them. Email confirmation is
off in `supabase/config.toml`, so signup logs you straight in.

Then apply the schema: `cd backend && alembic upgrade head`.

### Cloud project (deployment)

1. Go to [supabase.com](https://supabase.com) and create a new project
2. From Project Settings, copy the database connection string (**Session mode, port 5432**) and add it as `SUPABASE_DATABASE_URL`. The Transaction-mode pooler on port **6543** will not work: it multiplexes one server connection across clients, which breaks the server-side prepared statements SQLAlchemy's psycopg2 driver issues, and it does not support the `SET` statements a migration runs. The backend adds `sslmode=require` automatically for any host that is not loopback, so the URL needs no query string
3. From Project Settings > API, copy the `anon` key and add it as `VITE_SUPABASE_ANON_KEY`
4. From Project Settings > API, copy the JWT secret and add it as `SUPABASE_JWT_SECRET`, and the project URL as `SUPABASE_URL` (the backend verifies tokens against the project JWKS first and falls back to the shared secret)
5. From Project Settings > Auth, enable Google OAuth if you want Google login (requires a Google Cloud OAuth client)
6. Run `alembic upgrade head` to create all tables

---

## Azure AI Foundry Setup

1. Go to [portal.azure.com](https://portal.azure.com) and create an Azure AI Foundry resource
2. Deploy the `gpt-4o` model and note the deployment name
3. From the resource overview, copy the endpoint URL and add it as `AZURE_OPENAI_ENDPOINT`
4. From Keys and Endpoint, copy the API key and add it as `AZURE_OPENAI_API_KEY`
5. Set `AZURE_GPT4O_DEPLOYMENT` to the exact deployment name you used

---

## Groq Setup

1. Go to [console.groq.com](https://console.groq.com) and create an account
2. Generate an API key and add it as `GROQ_API_KEY`
3. No model deployment needed — Groq hosts `openai/gpt-oss-120b` directly. Set `GROQ_MODEL` if you want a different model; `llama-3.3-70b-versatile` from the original plan has been decommissioned by Groq.

---

## Deployment

### Backend — Render

`backend/render.yaml` is a Blueprint describing the whole service: Python 3.11.9,
`pip install -r requirements.txt`, a start command of
`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and
`/health` as the health check path. Every secret in it is `sync: false`, so
Render prompts for the values on the first deploy and none of them live in git.

Render reads `render.yaml` from the **repository root**, so either move or
symlink the file there, or create the Web Service from the dashboard and copy
the settings across by hand.

Two details are easy to get wrong:

- **Python version.** Render's Python runtime is pinned by the `PYTHON_VERSION`
  environment variable (`3.11.9` in the Blueprint), which must stay in step with
  `backend/.python-version`.
- **`$PORT`.** Render assigns the port at run time. Nothing in the application
  reads it — uvicorn takes it on the command line, which is why the start
  command must keep `--host 0.0.0.0 --port $PORT`.

Migrations run as part of the start command because the free tier has no
separate release phase. The `&&` is deliberate: a failed migration stops the
deploy rather than booting the app against an old schema.

`backend/Dockerfile` is the alternative for any host that takes an image
(`python:3.11-slim`, non-root, same start command).

### Frontend — Vercel

Connect the repo, set `VITE_API_URL` to the Render URL and the two
`VITE_SUPABASE_*` values in the Vercel dashboard.

### Production checklist

- [ ] `ALLOWED_ORIGINS` on Render is the Vercel URL (`https://<app>.vercel.app`),
      not `localhost` — without it every browser call fails CORS
- [ ] `SUPABASE_DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_JWT_SECRET` point at
      the **cloud** project, and the database URL is the Session-mode pooler
      (port 5432, not 6543)
- [ ] `AZURE_OPENAI_*` and `GROQ_API_KEY` are set — a missing key disables the
      provider fallback that covers the other one's rate limits
- [ ] Migrations have run: `alembic upgrade head` (the start command does this,
      so check the deploy log rather than assuming)
- [ ] `GET https://<render-url>/health` returns `"db": "ok"` — `"error"` means
      the app is up and cannot reach Postgres, usually a wrong pooler port or a
      password that was never URL-encoded
- [ ] `VITE_API_URL` on Vercel is the Render URL, and a request from the live
      frontend comes back with an `X-Request-ID` header

---

## Prompt Strategy

**Quick analysis** uses Groq with a structured prompt that instructs the model to compare the user's profile against the JD and return JSON with: fit_score, strengths (list of 3), gaps (list of 3), and a one-sentence verdict. Speed is prioritized.

**Detailed analysis** uses Azure GPT-4o with a longer prompt that asks for skill-by-skill comparison, gap reasoning per skill, and an overall fit narrative. Quality and depth are prioritized over speed.

**Chat** uses Groq with a context window built from the user's profile summary, the full JD, and the last N messages. The system prompt instructs the model to be proactive but not overwhelming — it suggests next steps after analysis but backs off if the user redirects.

**Output generation** (resume, cover letter, answers) uses Azure GPT-4o with prompts that instruct the model to ground every output strictly in the user's profile and the JD. No fabrication of experience or credentials is permitted.

**Provider fallback.** Groq's free tier has a daily token cap, and backoff cannot outwait a limit that resets at midnight — so every model call names a preferred provider and, when that provider is rate-limited, 5xx, or unreachable, is re-sent once to the other one with the same prompt, temperature, and token budget (`backend/app/services/llm.py`). A daily cap ("tokens per day", "TPD") skips the retries entirely and fails over immediately; a per-minute limit is backed off first. A 400/401/422 is our own request being wrong and is never retried elsewhere. Chat streams are the one asymmetric case: the swap is only safe *before the first token reaches the user*, because a reply whose halves came from two different models would contradict itself, so a mid-stream failure is surfaced as a partial reply exactly as before. Which provider served a request comes back on the SSE `done` event and in an analysis's `full_json._provider`. `LLM_FALLBACK_ENABLED=false` turns failover off; `LLM_PREFER_AZURE_FOR_CHAT=true` sends chat to Azure first, with no code change, for a day when Groq is capped from the first message.

---

## Tradeoffs

| Decision | Tradeoff |
|---|---|
| Groq for chat, Azure for analysis and outputs | Groq is faster and cheaper for conversational turns. Azure GPT-4o produces higher quality for longer, more structured outputs. The split optimizes for both. |
| Automatic fallback to the other provider on a rate limit | A capped Groq degrades to a slower, costlier Azure answer instead of a 502. The cost is that a request can quietly cost Azure tokens and read slightly differently in tone; `full_json._provider` and the SSE `done` event say which model answered, and `LLM_FALLBACK_ENABLED=false` turns it off. |
| No fallback once a chat stream has started | Switching models mid-reply would splice two different answers together in front of the user. A stream that fails after the first token keeps today's behaviour: the partial reply is persisted and an error event offers a retry. |
| Resumes parsed in memory, not stored | Simpler storage, but the original file is not recoverable. Only structured data is saved. |
| Supabase Auth instead of custom auth | Saves significant development time. Supabase handles JWTs, sessions, and OAuth. Backend only verifies the token. |
| No job listings | Applify is not a job board. Keeping listings out keeps the product focused and avoids the complexity of sourcing and maintaining fresh listings. |
| Sliding context window on long chats | Keeps token costs manageable for long conversations. Oldest messages are truncated first. The profile and JD are always included regardless of window size. |
| Free during beta, no usage limits | Lowers friction for early adopters. Monetization decisions made after learning what features users value most. |

---

## Project Documents

| Document | Description |
|---|---|
| `applify-problem-statement.md` | Problem, motivation, requirements, and scope |
| `applify-tech-stack.md` | Full stack with choices and reasoning |
| `applify-folder-structure.md` | Complete folder structure with file responsibilities |
| `applify-pipeline.md` | Phase-by-phase development pipeline with acceptance criteria |
| `README.md` | This file |

---

## License

Private. All rights reserved.
