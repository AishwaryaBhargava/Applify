# Applify
### Your Job Application Co-Pilot
**Tech Stack — V1.0**

---

## Overview

Applify is a web application with a React + Vite frontend deployed on Vercel and a Python FastAPI backend deployed on Render. AI capabilities are split between Groq (fast conversational responses) and Azure AI Foundry (deep analysis and document generation). User data and profiles are persisted in a Supabase Postgres database. Authentication is handled via Supabase Auth.

---

## Frontend

| Concern | Choice | Reason |
|---|---|---|
| Framework | React 18 + Vite + TypeScript | Fast dev server, type safety, strong ecosystem |
| Styling | Tailwind CSS | Utility-first, consistent design system, fast iteration |
| State management | Zustand | Lightweight, no boilerplate, easy async |
| HTTP client | Axios | Interceptors for auth headers, clean error handling |
| Icons | Lucide React | Clean SVG icons, tree-shakeable |
| Routing | React Router v6 | Simple page-level routing |
| Markdown rendering | react-markdown | For rendering AI chat responses cleanly |
| File upload | Native HTML input + Axios multipart | Sufficient for resume PDF/DOCX upload |

---

## Backend

| Concern | Choice | Reason |
|---|---|---|
| Framework | Python FastAPI | Async-native, fast, clean OpenAPI docs out of the box |
| Server | Uvicorn | ASGI server, required for FastAPI |
| Validation | Pydantic v2 | Schema validation, used natively by FastAPI |
| File handling | python-multipart | Required for FastAPI file uploads |
| Resume parsing | pdfplumber (PDF), python-docx (DOCX) | Reliable text extraction from both resume formats |
| Environment | python-dotenv | Load .env values locally |
| ORM | SQLAlchemy 2.0 | Async-compatible ORM, pairs naturally with FastAPI |
| Database driver | psycopg2-binary | PostgreSQL driver required by SQLAlchemy |
| Migrations | Alembic | Database migration tool, works with SQLAlchemy |
| Groq SDK | groq | Official Groq Python SDK for fast chat completions |
| Azure SDK | openai (Azure-compatible) | Azure AI Foundry uses the OpenAI SDK with an Azure endpoint |

---

## AI Layer

Groq handles fast conversational responses and quick analysis. Azure AI Foundry handles deep analysis and all document generation where quality matters more than speed.

| Feature | Model | Provider |
|---|---|---|
| Quick snapshot analysis | llama-3.3-70b-versatile | Groq |
| Conversational chat responses | llama-3.3-70b-versatile | Groq |
| Detailed breakdown analysis | GPT-4o | Azure AI Foundry |
| Resume generation | GPT-4o | Azure AI Foundry |
| Cover letter generation | GPT-4o | Azure AI Foundry |
| Application question help | GPT-4o | Azure AI Foundry |
| Profile gap nudges | llama-3.3-70b-versatile | Groq |

### Rate Limit Notes
- Groq free tier: generous limits, well suited for fast conversational responses
- Azure AI Foundry: per-minute token limits on GPT-4o. Detailed analysis and document generation are longer calls. Server-side retry with exponential backoff is implemented for all Azure calls.

---

## Database (Supabase)

Supabase provides managed Postgres and built-in authentication on a free tier. All user data is persisted server-side.

| Table | Purpose |
|---|---|
| users | Supabase Auth managed. Stores user id, email, created_at |
| profiles | One per user: parsed resume data, manual enrichments, raw profile JSON |
| job_chats | One per job opening: id, user_id, title, company, jd_text, analysis_type, created_at |
| chat_messages | Full message history per chat: id, chat_id, role, content, created_at |
| analyses | One per chat: id, chat_id, type (quick/detailed), fit_score, strengths, gaps, verdict, created_at |
| tracker_entries | One per chat: id, chat_id, user_id, status, resume_type, created_at, updated_at |
| generated_outputs | Stores AI-generated resumes, cover letters, and answers: id, chat_id, output_type, content, created_at |

---

## Authentication

| Concern | Choice | Reason |
|---|---|---|
| Auth provider | Supabase Auth | Built into Supabase, handles sessions, JWT, and social login out of the box |
| Supported methods | Email + password, Google OAuth | Email for simplicity, Google for low-friction signup |
| Session handling | Supabase client SDK (frontend) + JWT verification (backend) | Frontend manages session state, backend verifies token on every request |

---

## Infrastructure

| Concern | Choice |
|---|---|
| Frontend deploy | Vercel (connect GitHub repo, auto-deploy on push) |
| Backend deploy | Render (Web Service, free tier) |
| Database + Auth | Supabase (managed Postgres + Auth, free tier) |
| Environment variables | Vercel dashboard (frontend), Render dashboard (backend) |
| File storage | No persistent file storage — resumes are parsed in memory and discarded after extraction |

---

## Development Environment

| Tool | Version |
|---|---|
| Node.js | 18+ |
| Python | 3.11+ |
| npm | 9+ |
| pip | 23+ |

---

## Key Environment Variables

### Backend (.env)
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
- All AI context for a chat (profile + JD + chat history) is sent with every message. For very long chats this increases token usage. A sliding context window will be applied if chat history exceeds 4000 words.
- Alembic handles all schema changes via migrations. Never modify the database schema manually in Supabase — always go through a migration file.
