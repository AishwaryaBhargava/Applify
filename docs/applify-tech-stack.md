# Applify
### Your Job Application Co-Pilot
**Tech Stack — V1.0**

---

## Overview

Applify is a web application with a React + Vite frontend deployed on Vercel and a Python FastAPI backend deployed on Render. AI capabilities are split between Groq (fast conversational responses) and Azure AI Foundry (deep analysis and document generation), with automatic fallback between the two. User data and profiles are persisted in a Supabase Postgres database. Authentication is handled via Supabase Auth.

Every dependency is pinned to an exact version in `frontend/package.json` and `backend/requirements.txt`, so a clean install reproduces the tested build.

---

## Frontend

| Concern | Choice | Reason |
|---|---|---|
| Framework | React 18.3.1 + Vite 5.4 + TypeScript 5.6 | Fast dev server, type safety, strong ecosystem |
| Styling | Tailwind CSS 3.4 | Utility-first, consistent design system, fast iteration |
| State management | Zustand 4.5 | Lightweight, no boilerplate, easy async |
| HTTP client | Axios 1.7 | Interceptors for auth headers, clean error handling |
| Icons | Lucide React | Clean SVG icons, tree-shakeable |
| Routing | React Router v6 | Simple page-level routing, with `lazy` route-level code splitting |
| Markdown rendering | react-markdown 9 | For rendering AI chat responses cleanly |
| File upload | Native HTML input + Axios multipart | Sufficient for resume PDF/DOCX upload |
| Streaming | `fetch` + `ReadableStream` reader | `EventSource` cannot send an Authorization header or a POST body, so SSE frames are parsed by hand |

---

## Backend

| Concern | Choice | Reason |
|---|---|---|
| Framework | Python FastAPI 0.141 | Async-native, fast, clean OpenAPI docs out of the box |
| Server | Uvicorn | ASGI server, required for FastAPI |
| Validation | Pydantic 2.13 | Schema validation, used natively by FastAPI |
| Settings | pydantic-settings | One Settings class, all env vars in one place |
| File handling | python-multipart | Required for FastAPI file uploads |
| Resume parsing | pdfplumber (PDF), python-docx (DOCX) | Reliable text extraction from both resume formats |
| Environment | python-dotenv | Load .env values locally |
| ORM | SQLAlchemy 2.0.52 | Async-compatible ORM, pairs naturally with FastAPI |
| Database driver | psycopg2-binary | PostgreSQL driver required by SQLAlchemy |
| Migrations | Alembic 1.19 | Database migration tool, works with SQLAlchemy |
| JWT verification | PyJWT | Verifies Supabase tokens against the project JWKS or the legacy shared secret |
| Groq SDK | groq | Official Groq Python SDK for fast chat completions |
| Azure SDK | openai (Azure-compatible) | Azure AI Foundry uses the OpenAI SDK with an Azure endpoint |
| Tests | pytest | Route tests run against an in-memory fake session, no database required |

---

## AI Layer

Groq handles fast conversational responses and quick analysis. Azure AI Foundry handles deep analysis and all document generation where quality matters more than speed.

| Feature | Model | Provider |
|---|---|---|
| Quick snapshot analysis | openai/gpt-oss-120b | Groq |
| Conversational chat responses | openai/gpt-oss-120b | Groq |
| Resume extraction to structured JSON | openai/gpt-oss-120b | Groq |
| Intent classification (ambiguous messages only) | openai/gpt-oss-120b | Groq |
| Detailed breakdown analysis | GPT-4o | Azure AI Foundry |
| Resume generation | GPT-4o | Azure AI Foundry |
| Cover letter generation | GPT-4o | Azure AI Foundry |
| Application question help | GPT-4o | Azure AI Foundry |

The Groq model is set by `GROQ_MODEL` and defaults to `openai/gpt-oss-120b`. Profile gap nudges are rule-based and make no model call at all — the same profile always produces the same nudges, which is what makes a dismissal stick.

### Provider Fallback

Every model call names a preferred provider and falls back **once** to the other one when the preferred provider is rate-limited, 5xx, or unreachable (`backend/app/services/llm.py`). A 400/401/403/422 means our own request is wrong and is never retried elsewhere. Chat streams fail over only before the first token reaches the user; splicing two models mid-reply would contradict itself. Which provider served a request comes back on the SSE `done` event and in an analysis's `full_json._provider`.

### Rate Limit Notes
- Groq free tier: generous per-minute limits, but a **daily** token cap that backoff cannot outwait. A daily cap fails over to Azure immediately; a per-minute limit is backed off first.
- Azure AI Foundry: per-minute token limits on GPT-4o. Detailed analysis and document generation are longer calls. Server-side retry with exponential backoff is implemented for all Azure calls.

---

## Database (Supabase)

Supabase provides managed Postgres and built-in authentication on a free tier. All user data is persisted server-side. Development runs the whole stack locally in Docker via the Supabase CLI (`npx supabase start`); deployment uses a cloud Supabase project. The schema is identical either way — Alembic owns it in both.

| Table | Purpose |
|---|---|
| users | Supabase Auth managed. Stores user id, email, created_at |
| profiles | One per user: parsed resume data, manual enrichments, raw profile JSON |
| job_chats | One per job opening: id, user_id, title, company, jd_text, analysis_type, created_at, deleted_at (soft delete) |
| chat_messages | Full message history per chat: id, chat_id, role, content, kind, created_at |
| analyses | One per chat: id, chat_id, type (quick/detailed), fit_score, strengths, gaps, verdict, full_json, created_at |
| tracker_entries | One per chat: id, chat_id, user_id, status, resume_type, created_at, updated_at |
| generated_outputs | Stores AI-generated resumes, cover letters, and answers: id, chat_id, output_type, content, created_at |

`chat_messages.kind` records what produced a message — `chat`, `analysis`, `resume`, `cover_letter`, or `answer` — so the frontend can render each differently. `job_chats.deleted_at` makes deletion soft: the row and its tracker entry stay, and every read filters them out.

---

## Authentication

| Concern | Choice | Reason |
|---|---|---|
| Auth provider | Supabase Auth | Built into Supabase, handles sessions, JWT, and social login out of the box |
| Supported methods | Email + password, Google OAuth | Email for simplicity, Google for low-friction signup |
| Session handling | Supabase client SDK (frontend) + JWT verification (backend) | Frontend manages session state, backend verifies token on every request |
| Token verification | JWKS first (ES256/RS256), legacy HS256 secret as fallback | Supabase signs with asymmetric keys on new projects and a shared secret on older ones. The unverified header says which, so both work with no configuration flag |

---

## Infrastructure

| Concern | Choice |
|---|---|
| Frontend deploy | Vercel (connect GitHub repo, auto-deploy on push). `frontend/vercel.json` holds the build, SPA rewrites, cache and security headers |
| Backend deploy | Render (Web Service, free tier). `backend/render.yaml` is the Blueprint; `backend/Dockerfile` is the container alternative |
| Database + Auth | Supabase (managed Postgres + Auth, free tier) in production, the Supabase CLI stack in Docker for local development |
| Environment variables | Vercel dashboard (frontend), Render dashboard (backend) |
| File storage | No persistent file storage — resumes are parsed in memory and discarded after extraction |

---

## Development Environment

| Tool | Version |
|---|---|
| Node.js | 18+ |
| Python | 3.11 (the version Render runs, pinned in `backend/.python-version`; 3.10 works but 3.11 is the target) |
| npm | 9+ |
| pip | 23+ |
| Docker Desktop | Required only for the local Supabase stack |

---

## Key Environment Variables

### Backend (.env)
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
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_JWT_SECRET=<your-supabase-jwt-secret>
ALLOWED_ORIGINS=http://localhost:5173
LOG_LEVEL=INFO
```

`SUPABASE_URL` is what the JWKS lookup is built from. `APP_VERSION` is an optional override for the build id `GET /health` reports; left unset, the backend falls back to `RENDER_GIT_COMMIT`, then the checked-out git sha, then `"dev"`.

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<your-project>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

---

## Notable Constraints and Tradeoffs

- Resumes are parsed in memory and not stored as files. Only the extracted structured data is saved to the database. This simplifies storage but means the original file is not retrievable.
- Render free tier has a cold start delay of approximately 30 seconds after inactivity. Acceptable for V1.
- Supabase free tier supports up to 500MB of database storage and 2GB of bandwidth per month. Sufficient for V1.
- Azure GPT-4o calls for detailed analysis and document generation are longer and more expensive per call than Groq. This is acceptable in V1 since the product is free and usage is expected to be moderate during beta.
- Automatic fallback between providers means a rate-limited Groq degrades to a slower, costlier Azure answer instead of a 502. The cost is that a request can quietly spend Azure tokens and read slightly differently in tone; `LLM_FALLBACK_ENABLED=false` turns it off, and the provider that answered is always reported.
- All AI context for a chat (profile + JD + chat history) is sent with every message. A 4000-word sliding window is applied to chat history, dropping the oldest turns first; the profile, JD, and analysis live in the system message and are never dropped. Output generation uses the same window at a 6000-word budget.
- Alembic handles all schema changes via migrations. Never modify the database schema manually in Supabase — always go through a migration file.
