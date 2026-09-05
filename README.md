# Applify

### Your Job Application Co-Pilot

Applify is a dedicated AI workspace for job applications. Every job opening gets
its own chat, and your professional profile is always in context, so you never
re-paste a resume or re-explain your background. Paste a job description and
Applify analyses your fit against it, generates a tailored resume, cover letter,
or application answer on demand, and tracks the application from *Not applied*
through to *Offer*. It is not a job board and it does not apply on your behalf:
it is the preparation and analysis layer that general-purpose AI chat is not
built for.

## Screenshots

| | |
|---|---|
| ![Landing page](docs/screenshots/landing.png) | ![Job chat with fit analysis](docs/screenshots/chat-analysis.png) |
| Public landing page for signed-out visitors | A job chat: JD, fit analysis card, generated outputs, generate buttons |
| ![Profile](docs/screenshots/profile.png) | ![Application tracker](docs/screenshots/tracker.png) |
| The parsed profile with a completeness meter and per-section editing | The tracker: status, analysis depth, fit score, resume type |

<img src="docs/screenshots/chat-mobile.png" alt="Job chat on a 375px viewport" width="280">

The same chat at 375px. Every page is responsive down to 320px.

## Features

- **Resume to structured profile.** Upload a PDF or DOCX and Applify parses it in
  memory into summary, experience, education, skills, certifications, projects,
  and achievements. A completeness meter and rule-based gap nudges point at what
  is thin or missing.
- **Manual enrichment.** Every profile section is editable, with explicit Save
  and Discard per section, client-side validation, and matching strict validation
  on the API.
- **One chat per job.** A chat is created from a title, an optional company, and
  the job description. Chats are isolated from each other and listed in the
  sidebar.
- **Fit analysis, two depths.** A quick snapshot (fit score, three strengths,
  three gaps, one-line verdict) runs on Groq; a detailed breakdown
  (skill-by-skill comparison, gap reasoning, suggestions) runs on Azure GPT-4o.
- **Streaming chat.** Replies stream token by token over SSE, grounded in the
  profile, the full JD, and a sliding window of the conversation.
- **Tailored outputs.** Resume, cover letter, and application-answer help, from
  either an explicit button or a request typed into the chat. Outputs stream, are
  persisted per chat, and can be copied or downloaded.
- **Application tracker.** One row per chat, created automatically. Status
  (`not_applied`, `applied`, `interviewing`, `offer`, `rejected`) is user-set;
  job title, company, date, analysis depth, fit score, and resume type
  (Unaltered or AI-Tailored) follow the chat.
- **Auth and settings.** Supabase email and Google sign-in, plus a settings page
  for the account, the default analysis depth, and sign out.
- **Responsive, light-only UI.** Audited from 320px to 1920px.

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | React 18.3.1, TypeScript 5.6.3, Vite 5.4.11, Tailwind CSS 3.4.17, react-router-dom 6.28.1, Zustand 4.5.5, react-markdown 9.0.1, axios 1.7.9 |
| Backend | Python 3.11, FastAPI 0.141.1, Uvicorn 0.52.4, SQLAlchemy 2.0.52, Alembic 1.19.2, Pydantic 2.13.5, PyJWT 2.13.0 |
| Resume parsing | pdfplumber 0.11.10 (PDF), python-docx 1.2.0 (DOCX) |
| Database and auth | Supabase (Postgres 17) with Supabase Auth, psycopg2-binary 2.9.12 |
| AI, fast path | Groq SDK 1.7.0, model `openai/gpt-oss-120b` |
| AI, quality path | Azure AI Foundry GPT-4o via openai 3.8.0 |
| Hosting | Vercel (frontend), Render or any Docker host (backend), Supabase cloud (database and auth) |

## Architecture

A React single-page app talks to a FastAPI service, which owns all persistence in
Postgres through SQLAlchemy and Alembic. Supabase Auth issues the JWT; the
frontend attaches it as a bearer token and the backend verifies it against the
project JWKS first, falling back to the legacy HS256 shared secret, because local
Supabase signs with ES256 keys while a cloud project may not. Every route except
`GET /health` requires that token, and every chat-scoped query is filtered by
`user_id` and `deleted_at IS NULL`, so someone else's chat is a 404 rather than a
403. Model calls go through one client that names a preferred provider per call
(Groq for chat, quick analysis, and resume extraction; Azure GPT-4o for the
detailed analysis and generated documents) and falls back once to the other
provider on a rate limit, 5xx, or timeout. Chat replies and generated documents
stream as SSE, read in the browser with a `fetch` reader rather than
`EventSource` so the request can carry an `Authorization` header; analysis is a
single JSON response. Uploaded resumes are parsed in memory and discarded, and
only the extracted text and structured JSON are stored. The full endpoint
contract is in [`backend/API.md`](backend/API.md).

## Local development

### Prerequisites

- Node.js 18+
- Python 3.11 (3.10 works; 3.11 is what Render runs)
- Docker Desktop, for the local Supabase stack
- Supabase CLI, used through `npx`, so nothing to install
- A Groq API key ([console.groq.com](https://console.groq.com))
- An Azure AI Foundry resource with a `gpt-4o` deployment

A cloud Supabase project is a deployment concern only. Development runs the whole
Supabase stack in Docker.

### 1. Clone

```bash
git clone https://github.com/AishwaryaBhargava/Applify.git
cd Applify
```

### 2. Start Supabase

```bash
npx supabase start   # first run pulls ~10 images, several minutes
npx supabase status  # reprints the values below at any time
npx supabase stop    # data is kept; add --no-backup to wipe the database
```

`start` and `status` print the three values the apps need. They are the CLI's
public demo credentials, already filled into both `.env.example` files:

| Printed value | Where it goes |
|---|---|
| `DB_URL` (`postgresql://postgres:postgres@127.0.0.1:54322/postgres`) | `SUPABASE_DATABASE_URL` |
| `API_URL` (`http://127.0.0.1:54321`) | `SUPABASE_URL` and `VITE_SUPABASE_URL` |
| `ANON_KEY` or `PUBLISHABLE_KEY` | `VITE_SUPABASE_ANON_KEY` |

`JWT_SECRET` is printed too and maps to `SUPABASE_JWT_SECRET`, but local tokens
are signed with ES256 signing keys, so the backend's JWKS path is what actually
verifies them. Email confirmation is off in `supabase/config.toml`, so signup
logs you straight in.

### 3. Backend

```bash
cd backend
py -3.11 -m venv venv          # macOS/Linux: python3.11 -m venv venv
source venv/Scripts/activate   # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # then fill in the Groq and Azure values
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`--reload` is optional. On Windows the watchfiles reloader can wedge on a save;
drop the flag and restart by hand if that happens.

Confirm the service:

```bash
curl http://localhost:8000/health
# {"status":"ok","db":"ok","version":"a9f815b"}
```

`status` is liveness and stays `ok` while the process answers. `db` is a
`SELECT 1` with a two-second ceiling, so an unreachable database reads as
`"db":"error"` on a 200 rather than a failed request, and Render will not recycle
a healthy instance over a database blip. `version` is the running build's short
git sha, or `dev` when there is no git metadata.

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### URLs

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| Supabase Studio | http://127.0.0.1:54323 |
| Mailpit, local mailbox | http://127.0.0.1:54324 |
| Postgres | postgresql://postgres:postgres@127.0.0.1:54322/postgres |

### Tests and checks

```bash
cd backend
source venv/Scripts/activate   # macOS/Linux: source venv/bin/activate
pytest app/tests -q
# 299 passed, 7 skipped in ~3s
```

The 7 skips are opt-in integration tests: `RUN_LIVE=1` runs the ones that make
real Groq and Azure calls, `RUN_DB=1` runs the ones that need a live Postgres.

```bash
cd frontend
npm run lint     # eslint
npm run build    # tsc -b && vite build, output in dist/
```

## Environment variables

### Backend (`backend/.env`)

| Variable | Secret | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | no | Azure AI Foundry endpoint, `https://<resource>.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | yes | Azure AI Foundry key |
| `AZURE_OPENAI_API_VERSION` | no | API version, `2024-12-01-preview` |
| `AZURE_GPT4O_DEPLOYMENT` | no | Exact GPT-4o deployment name, default `gpt-4o` |
| `GROQ_API_KEY` | yes | Groq API key |
| `GROQ_MODEL` | no | Groq model id, default `openai/gpt-oss-120b` |
| `LLM_FALLBACK_ENABLED` | no | `true` fails a rate-limited or unreachable provider over to the other one |
| `LLM_PREFER_AZURE_FOR_CHAT` | no | `true` sends chat to Azure GPT-4o first instead of Groq |
| `SUPABASE_DATABASE_URL` | yes | Postgres connection string. `sslmode=require` is added automatically for any non-loopback host |
| `SUPABASE_URL` | no | Supabase project or local API URL, used to fetch the JWKS |
| `SUPABASE_JWT_SECRET` | yes | Legacy HS256 secret, the fallback when JWKS verification does not apply |
| `ALLOWED_ORIGINS` | no | Comma-separated CORS origins, matched against the browser `Origin` header by exact string. A trailing slash or missing scheme is corrected at startup and logged |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

### Frontend (`frontend/.env`)

| Variable | Secret | Description |
|---|---|---|
| `VITE_API_URL` | no | Backend base URL, `http://localhost:8000` in development |
| `VITE_SUPABASE_URL` | no | Supabase project or local API URL |
| `VITE_SUPABASE_ANON_KEY` | no | Anon or publishable key. Public by design; every `VITE_` value ships in the bundle |

## Deployment

### Supabase cloud project

1. Create a project at [supabase.com](https://supabase.com).
2. Copy the database connection string in **Session mode, port 5432** into
   `SUPABASE_DATABASE_URL`. The Transaction-mode pooler on 6543 will not work: it
   multiplexes one server connection across clients, which breaks the server-side
   prepared statements the psycopg2 driver issues, and it does not support the
   `SET` statements a migration runs.
3. From Project Settings > API, copy the project URL into `SUPABASE_URL` and
   `VITE_SUPABASE_URL`, the anon key into `VITE_SUPABASE_ANON_KEY`, and the JWT
   secret into `SUPABASE_JWT_SECRET`. Verification uses the project JWKS
   automatically; the secret is only the fallback.
4. Under Authentication, enable Email and, for Google sign-in, the Google
   provider (needs a Google Cloud OAuth client).

### Backend on Render

[`backend/render.yaml`](backend/render.yaml) is a Blueprint for the whole
service: `PYTHON_VERSION` 3.11.9 (kept in step with `backend/.python-version`),
`pip install -r requirements.txt`, `/health` as the health check path, and a
start command of
`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
Migrations run in the start command because the free tier has no release phase,
and the `&&` is deliberate: a failed migration stops the deploy rather than
booting the app against an old schema. Every secret is `sync: false`, so Render
prompts for the values and none of them live in git.

Render reads `render.yaml` from the **repository root**, so either move or
symlink it there, or create the Web Service from the dashboard and copy the
settings across by hand.

Any host that takes an image can use [`backend/Dockerfile`](backend/Dockerfile)
instead (`python:3.11-slim`, non-root, same migrate-then-serve command).

### Frontend on Vercel

Import the repo, set the **root directory** to `frontend`, and add `VITE_API_URL`
(the Render URL), `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`.
[`frontend/vercel.json`](frontend/vercel.json) already sets the Vite preset, the
SPA rewrite, asset caching, and security headers. Once the frontend has a URL,
set `ALLOWED_ORIGINS` on Render to it.

### Production checklist

- [ ] `ALLOWED_ORIGINS` on Render is the Vercel URL (`https://<app>.vercel.app`),
      not `localhost`. Without it every browser call fails CORS.
- [ ] `SUPABASE_DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_JWT_SECRET` point at
      the cloud project, and the database URL is the Session-mode pooler on 5432.
- [ ] `AZURE_OPENAI_*` and `GROQ_API_KEY` are both set. A missing key disables the
      fallback that covers the other provider's rate limits.
- [ ] `GET https://<render-url>/health` returns `"db":"ok"`. `"error"` means the
      app is up but cannot reach Postgres, usually the wrong pooler port or a
      password that was never URL-encoded.
- [ ] `VITE_API_URL` on Vercel is the Render URL, and a request from the live
      frontend comes back with an `X-Request-ID` header.

## Project documents

| Document | Contents |
|---|---|
| [`docs/applify-problem-statement.md`](docs/applify-problem-statement.md) | Problem, motivation, requirements, scope |
| [`docs/applify-tech-stack.md`](docs/applify-tech-stack.md) | Stack choices and reasoning |
| [`docs/applify-folder-structure.md`](docs/applify-folder-structure.md) | Folder structure with per-file responsibilities |
| [`docs/applify-pipeline.md`](docs/applify-pipeline.md) | Phase-by-phase build log, acceptance criteria, deviations |
| [`backend/API.md`](backend/API.md) | Endpoint contract, error shapes, SSE wire format |
| [`designs/00-index.html`](designs/00-index.html) | Static HTML design references for every page |

## Notable decisions

- **Local Supabase for development.** The whole stack runs in Docker via the CLI,
  so nobody needs a cloud project to run the app, and the schema is applied by
  Alembic rather than by hand.
- **JWKS-first token verification.** Local Supabase signs access tokens with
  ES256 signing keys rather than the legacy shared secret, so the backend tries
  the project JWKS first and only then `SUPABASE_JWT_SECRET`.
- **Groq model swap and provider fallback.** The planned
  `llama-3.3-70b-versatile` was decommissioned mid-build, so the Groq model is
  `openai/gpt-oss-120b`. Groq's free tier also has a daily token cap that backoff
  cannot outwait, so every call falls back once to the other provider. A daily cap
  fails over immediately; a per-minute limit is backed off first. A stream that
  has already emitted a token is never swapped, because splicing two models into
  one reply would contradict itself.
- **Analysis is JSON, chat and outputs stream.** The plan assumed the detailed
  analysis streamed. It is a single response behind a skeleton card instead,
  which keeps the structured JSON parseable; only chat replies and generated
  documents stream.
- **Rule-based gap detection.** Planned as AI-powered. Rules won because the same
  profile has to produce the same nudges every time, or a dismissed nudge comes
  back under different wording.
- **Explicit Save and Discard on profile sections,** not save-on-blur. Required
  fields are validated client-side and again by `PATCH /profile`, which returns a
  structured 422 instead of silently dropping incomplete entries. Unsaved changes
  are guarded on in-app navigation and on page unload.
- **Outputs have buttons as well as chat intent detection.** Both share one code
  path, and the button path writes the user turn it stands for, so the thread
  reads the same either way.
- **Light-only theme.** `color-scheme: light` is enforced rather than shipping a
  half-tested dark mode.
- **Python 3.11 everywhere.** Pinned in `backend/.python-version` and as
  `PYTHON_VERSION` in `render.yaml`, so local matches Render. 3.10 works, 3.11 is
  the target.
- **Resumes are never stored.** Uploads are parsed in memory and discarded; only
  the extracted text and structured JSON are persisted.

## License

Private. All rights reserved.
