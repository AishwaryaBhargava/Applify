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
| AI — Fast | Groq (llama-3.3-70b-versatile) |
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
python -m venv venv
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
# { "status": "ok" }
```

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
SUPABASE_DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<dbname>
SUPABASE_JWT_SECRET=<your-supabase-jwt-secret>
ALLOWED_ORIGINS=http://localhost:5173
```

### Frontend (`frontend/.env`)

```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<your-project>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

---

## Supabase Setup

1. Go to [supabase.com](https://supabase.com) and create a new project
2. From Project Settings, copy the database connection string (Session mode, port 5432) and add it as `SUPABASE_DATABASE_URL`
3. From Project Settings > API, copy the `anon` key and add it as `VITE_SUPABASE_ANON_KEY`
4. From Project Settings > API, copy the JWT secret and add it as `SUPABASE_JWT_SECRET`
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
3. No model deployment needed — Groq hosts `llama-3.3-70b-versatile` directly

---

## Prompt Strategy

**Quick analysis** uses Groq with a structured prompt that instructs the model to compare the user's profile against the JD and return JSON with: fit_score, strengths (list of 3), gaps (list of 3), and a one-sentence verdict. Speed is prioritized.

**Detailed analysis** uses Azure GPT-4o with a longer prompt that asks for skill-by-skill comparison, gap reasoning per skill, and an overall fit narrative. Quality and depth are prioritized over speed.

**Chat** uses Groq with a context window built from the user's profile summary, the full JD, and the last N messages. The system prompt instructs the model to be proactive but not overwhelming — it suggests next steps after analysis but backs off if the user redirects.

**Output generation** (resume, cover letter, answers) uses Azure GPT-4o with prompts that instruct the model to ground every output strictly in the user's profile and the JD. No fabrication of experience or credentials is permitted.

---

## Tradeoffs

| Decision | Tradeoff |
|---|---|
| Groq for chat, Azure for analysis and outputs | Groq is faster and cheaper for conversational turns. Azure GPT-4o produces higher quality for longer, more structured outputs. The split optimizes for both. |
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
