# Applify
### Your Job Application Co-Pilot
**Folder Structure — V1.0**

---

## Full Structure

```
applify/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py               # GET /health — liveness, db reachability, build sha
│   │   │   │   ├── auth.py                 # POST /auth/verify — confirms the backend accepts a token
│   │   │   │   ├── profile.py              # POST /profile/upload, GET /profile, PATCH /profile, GET /profile/gaps
│   │   │   │   ├── chats.py                # POST /chats, GET /chats, GET /chats/{id}, DELETE /chats/{id}
│   │   │   │   ├── messages.py             # GET /chats/{id}/messages, POST /chats/{id}/messages (SSE)
│   │   │   │   ├── analysis.py             # POST /chats/{id}/analyze?force= — non-streaming JSON
│   │   │   │   ├── outputs.py              # POST /chats/{id}/outputs (SSE), GET /chats/{id}/outputs
│   │   │   │   └── tracker.py              # GET /tracker, PATCH /tracker/{chat_id}
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py               # HealthResponse
│   │   │   │   ├── profile.py              # ParsedProfile, ProfileResponse, ProfileUpdateRequest, ProfileGap
│   │   │   │   ├── chats.py                # ChatCreateRequest, ChatResponse, ChatDetailResponse
│   │   │   │   ├── messages.py             # MessageRequest, MessageResponse
│   │   │   │   ├── analysis.py             # AnalysisRequest, AnalysisResponse, QuickSnapshot, DetailedBreakdown
│   │   │   │   ├── outputs.py              # OutputRequest, OutputResponse, OutputType enum
│   │   │   │   └── tracker.py              # TrackerEntry, TrackerUpdateRequest
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py                   # Settings class, loads all env vars via pydantic-settings
│   │   │   ├── errors.py                   # Exception handlers — one JSON shape for every failure
│   │   │   ├── logging.py                  # Root logger config, request id stamped on every line
│   │   │   ├── middleware.py               # Request id, security headers, body cap, safety net (raw ASGI)
│   │   │   └── version.py                  # Build id for /health: APP_VERSION, RENDER_GIT_COMMIT, git sha, "dev"
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── database.py                 # SQLAlchemy engine, SessionLocal, Base
│   │   │   └── deps.py                     # get_db and get_current_user dependencies for route injection
│   │   ├── models/
│   │   │   ├── __init__.py                 # Imports all models so Alembic can detect them
│   │   │   ├── profile.py                  # Profile model
│   │   │   ├── job_chat.py                 # JobChat model (soft delete via deleted_at)
│   │   │   ├── chat_message.py             # ChatMessage model (role + kind)
│   │   │   ├── analysis.py                 # Analysis model
│   │   │   ├── tracker_entry.py            # TrackerEntry model
│   │   │   └── generated_output.py         # GeneratedOutput model
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py                      # Provider abstraction — complete_json / stream_text, Groq-Azure fallback
│   │   │   ├── azure_client.py             # Shared Azure OpenAI client instance
│   │   │   ├── groq_client.py              # Shared Groq client instance
│   │   │   ├── resume_parser.py            # PDF and DOCX resume parsing logic
│   │   │   ├── profile_service.py          # Profile enrichment, rule-based gap detection
│   │   │   ├── analysis_service.py         # Quick snapshot and detailed breakdown logic
│   │   │   ├── chat_service.py             # Intent detection + conversational chat with streaming logic
│   │   │   └── output_service.py           # Resume, cover letter, and answer generation logic
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── conftest.py                 # FakeSession and shared fixtures — no database in the test env
│   │   │   ├── fixtures/
│   │   │   │   └── __init__.py             # Fictional resume plus in-memory PDF and DOCX builders
│   │   │   ├── test_health.py
│   │   │   ├── test_profile.py
│   │   │   ├── test_analysis.py
│   │   │   ├── test_chat.py
│   │   │   ├── test_outputs.py
│   │   │   ├── test_tracker.py
│   │   │   ├── test_llm.py                 # Provider fallback rules
│   │   │   └── test_errors.py              # Error shape, headers, body cap
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                     # JWT decode — JWKS first (ES256), HS256 secret as fallback
│   │   │   ├── context_builder.py          # Builds AI context from profile + JD + chat history
│   │   │   └── retry.py                    # Exponential backoff for Azure and Groq rate limits
│   │   ├── main.py                         # FastAPI app, logging, middleware, error handlers, routers
│   │   └── __init__.py
│   ├── alembic/
│   │   ├── versions/
│   │   │   ├── b7f2c9a41d38_initial_schema.py             # The six tables
│   │   │   └── c3a91f4b27d5_add_kind_to_chat_messages.py  # chat_messages.kind
│   │   ├── README
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── alembic.ini
│   ├── API.md                              # Full endpoint contract: shapes, statuses, SSE wire format
│   ├── Dockerfile                          # python:3.11-slim, non-root, migrate-then-serve
│   ├── render.yaml                         # Render Blueprint for the backend Web Service
│   ├── .env
│   ├── .env.example
│   ├── .gitignore
│   ├── .python-version                     # 3.11.9 — must match PYTHON_VERSION in render.yaml
│   └── requirements.txt
│
├── frontend/
│   ├── public/
│   │   └── applify-logo.svg                # Logo asset
│   ├── src/
│   │   ├── assets/
│   │   │   ├── icons/
│   │   │   │   ├── google.svg
│   │   │   │   └── logo-icon.svg
│   │   │   ├── logo.svg
│   │   │   └── logo-white.svg               # Light treatment for the deep teal panels
│   │   ├── components/
│   │   │   ├── auth/
│   │   │   │   ├── LoginForm.tsx            # Email + password login form
│   │   │   │   ├── SignupForm.tsx           # Email + password signup form
│   │   │   │   ├── GoogleButton.tsx         # Google OAuth sign-in button
│   │   │   │   ├── AuthMessage.tsx          # Inline error / success / info line on the auth forms
│   │   │   │   └── AuthPitchPanel.tsx       # Deep teal pitch panel beside the login and signup forms
│   │   │   ├── chat/
│   │   │   │   ├── ChatMessage.tsx          # Individual message bubble (user / assistant)
│   │   │   │   ├── ChatInput.tsx            # Message input bar with send button
│   │   │   │   ├── ChatThread.tsx           # Scrollable message thread
│   │   │   │   ├── TypingIndicator.tsx      # Dots between send and the first streamed token
│   │   │   │   ├── AnalysisTypeSelector.tsx # Quick snapshot vs detailed breakdown picker
│   │   │   │   ├── AnalysisCard.tsx         # Renders a completed analysis, quick or detailed
│   │   │   │   ├── AnalysisSkeleton.tsx     # Placeholder in the card's shape while one runs
│   │   │   │   ├── JobDescriptionPanel.tsx  # The pasted JD, collapsible
│   │   │   │   ├── NewChatModal.tsx         # Title, company, and JD paste for a new job chat
│   │   │   │   ├── OutputActions.tsx        # Explicit resume / cover letter / answer buttons
│   │   │   │   └── OutputsPanel.tsx         # Documents generated in this chat, with download
│   │   │   ├── profile/
│   │   │   │   ├── ResumeUpload.tsx         # Drag-and-drop or file picker for resume upload
│   │   │   │   ├── ProfileSection.tsx       # Reusable section card (experience, skills, etc.)
│   │   │   │   ├── ProfileField.tsx         # Editable field within a profile section
│   │   │   │   ├── ProfileEntryList.tsx     # Add / remove / edit a list of structured entries
│   │   │   │   ├── ProfileChips.tsx         # Tag editor for skills and achievements
│   │   │   │   ├── ProfileCompleteness.tsx  # Completeness score derived from the gap list
│   │   │   │   ├── ProfileSkeleton.tsx      # Loading placeholder for the profile page
│   │   │   │   ├── ProfileGapNudge.tsx      # Inline nudge when a profile section is thin
│   │   │   │   └── ResumeNudgeBanner.tsx    # Banner shown after onboarding was skipped
│   │   │   ├── tracker/
│   │   │   │   ├── TrackerTable.tsx         # Full tracker table with all job entries
│   │   │   │   ├── TrackerRow.tsx           # Single tracker row with status and resume type
│   │   │   │   ├── TrackerStats.tsx         # Summary tiles above the table
│   │   │   │   ├── TrackerFilters.tsx       # Status filter pills with counts
│   │   │   │   ├── StatusPicker.tsx         # Dropdown for updating application status
│   │   │   │   └── statuses.ts              # Status labels and display order, shared
│   │   │   ├── sidebar/
│   │   │   │   ├── Sidebar.tsx              # Full sidebar shell
│   │   │   │   ├── NavItem.tsx              # Individual navigation link
│   │   │   │   ├── ChatList.tsx             # List of job chats in the sidebar
│   │   │   │   └── NewChatButton.tsx        # Button to start a new job chat
│   │   │   └── common/
│   │   │       ├── TopBar.tsx               # Page header with title and actions
│   │   │       ├── Logo.tsx                 # Applify mark and wordmark, default and light
│   │   │       ├── Toast.tsx                # Non-blocking error and info notification
│   │   │       ├── ToastHost.tsx            # The single mount point that draws them
│   │   │       ├── Spinner.tsx              # Loading spinner
│   │   │       ├── Badge.tsx                # Status badge (Applied, Interviewing, etc.)
│   │   │       ├── ConfirmModal.tsx         # Generic confirmation dialog
│   │   │       ├── ErrorBoundary.tsx        # Catches a render crash instead of a blank page
│   │   │       └── BackendStatus.tsx        # Connection pill driven by GET /health
│   │   ├── pages/
│   │   │   ├── Landing.tsx                  # Public marketing page at /
│   │   │   ├── Login.tsx                    # Login page
│   │   │   ├── Signup.tsx                   # Signup page
│   │   │   ├── Onboarding.tsx               # Resume upload and initial profile setup
│   │   │   ├── Chat.tsx                     # Active job chat page
│   │   │   ├── Profile.tsx                  # Full profile view and edit page
│   │   │   ├── Tracker.tsx                  # Job application tracker page
│   │   │   └── Settings.tsx                 # Account, default analysis depth, sign out
│   │   ├── services/
│   │   │   ├── api.ts                       # Axios instance, base URL, auth header interceptor
│   │   │   ├── profile.ts                   # Calls the /profile routes
│   │   │   ├── chats.ts                     # Calls the /chats routes
│   │   │   ├── messages.ts                  # Calls GET and POST /chats/{id}/messages
│   │   │   ├── analysis.ts                  # Calls POST /chats/{id}/analyze
│   │   │   ├── outputs.ts                   # Calls GET and POST /chats/{id}/outputs
│   │   │   └── tracker.ts                   # Calls GET /tracker, PATCH /tracker/{chat_id}
│   │   ├── store/
│   │   │   ├── authStore.ts                 # Supabase session, user object, login/logout actions
│   │   │   ├── profileStore.ts              # Parsed profile data, enrichment state, dismissed nudges
│   │   │   ├── chatStore.ts                 # Active chat: messages, analysis, streaming state
│   │   │   ├── chatListStore.ts             # All user chats for sidebar list
│   │   │   ├── trackerStore.ts              # All tracker entries
│   │   │   ├── uiStore.ts                   # Chrome-level UI state (mobile sidebar drawer)
│   │   │   ├── toastStore.ts                # Toast queue, raised from anywhere
│   │   │   ├── session.ts                   # endSession — clears every store and persisted key
│   │   │   └── sessionExpired.ts            # Single handler for a 401 after a session existed
│   │   ├── hooks/
│   │   │   ├── useAuth.ts                   # Auth state helpers, redirect logic
│   │   │   ├── useStream.ts                 # Handles SSE streaming from backend AI responses
│   │   │   ├── useAutoScroll.ts             # Auto-scroll to bottom in chat thread
│   │   │   └── useProfileSectionEditor.ts   # Debounced section editing with save status
│   │   ├── types/
│   │   │   └── index.ts                     # Shared TypeScript interfaces: Profile, JobChat, Message, TrackerEntry, Analysis, GeneratedOutput
│   │   ├── styles/
│   │   │   └── global.css                   # Tailwind directives + CSS variables
│   │   ├── lib/
│   │   │   ├── supabase.ts                  # Supabase client instance
│   │   │   ├── validation.ts                # Shared client-side form validation
│   │   │   ├── format.ts                    # Relative dates and other display formatting
│   │   │   ├── download.ts                  # Hands the browser a generated document to save
│   │   │   ├── navigation.ts                # Router handle for code outside React (Axios interceptor)
│   │   │   └── preferences.ts               # Per-browser preferences, e.g. default analysis depth
│   │   ├── App.tsx                          # Router setup, layout shell, auth guard, code splitting
│   │   ├── main.tsx                         # React entry point
│   │   └── vite-env.d.ts
│   ├── .env
│   ├── .env.example
│   ├── .gitignore
│   ├── eslint.config.js
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vercel.json                          # Vercel build, SPA rewrites, cache and security headers
│   └── vite.config.ts
│
├── supabase/
│   ├── config.toml                          # Local Supabase stack: ports, auth settings, mail catcher
│   └── .gitignore
│
├── designs/                                 # Static HTML design references, one per screen
├── docs/                                    # The five project documents
├── .gitattributes                           # LF line endings for every text file
├── .gitignore
└── README.md
```

---

## Key File Responsibilities

### Backend

| File | Responsibility |
|---|---|
| `main.py` | Creates the FastAPI app, configures logging, assembles the middleware stack, registers exception handlers, mounts all routers |
| `core/config.py` | Single Settings class using pydantic-settings. All env vars loaded here, including CORS origin normalisation |
| `core/errors.py` | Exception handlers that give database failures, surviving rate limits, and unexpected errors the same `{"detail": "..."}` shape a route's `HTTPException` produces |
| `core/logging.py` | Configures the root logger and stamps every record with the request id |
| `core/middleware.py` | Raw ASGI middleware (not `BaseHTTPMiddleware`, which would buffer SSE): request id, security headers, request body cap, unhandled-exception net |
| `core/version.py` | Resolves the build identifier `/health` reports: `APP_VERSION`, then `RENDER_GIT_COMMIT`, then the git sha read from `.git`, then `"dev"` |
| `data/database.py` | SQLAlchemy engine, SessionLocal, and declarative Base |
| `data/deps.py` | FastAPI dependencies: get_db injects a database session, get_current_user verifies the JWT and returns the user id |
| `services/llm.py` | The one door every model call goes through. `complete_json` and `stream_text` take a preferred provider and fall back once to the other on a rate limit, 5xx, or dropped connection |
| `services/azure_client.py` | Instantiates one shared AzureOpenAI client used by analysis and output services |
| `services/groq_client.py` | Instantiates one shared Groq client used by chat and quick analysis services |
| `services/resume_parser.py` | Receives uploaded file bytes, detects PDF or DOCX, extracts structured text, returns parsed profile dict |
| `services/profile_service.py` | Profile merge logic and rule-based gap detection. Rules rather than a model call, so a dismissed nudge stays dismissed |
| `services/analysis_service.py` | Builds prompt from profile + JD, prefers Groq (quick) or Azure (detailed), normalises sloppy model output, returns structured analysis |
| `services/chat_service.py` | Classifies intent, builds context via `context_builder`, streams the reply, delegates to `output_service` when a document was asked for |
| `services/output_service.py` | Generates resume, cover letter, or application answer via Azure GPT-4o. Streams response and persists the output row |
| `utils/auth.py` | Decodes a Supabase token: JWKS first for asymmetric signing keys (ES256/RS256), the legacy HS256 secret as fallback |
| `utils/context_builder.py` | Assembles the full AI context from profile, JD text, and chat history. Applies the 4000-word sliding window, dropping oldest history first |
| `utils/retry.py` | Wraps Azure and Groq calls with exponential backoff on rate limit errors (429) |
| `tests/conftest.py` | `FakeSession`, an in-memory stand-in that evaluates real SQLAlchemy filters, plus the dependency overrides route tests run against |
| `tests/fixtures/` | A fictional resume and in-memory PDF/DOCX builders — no network, no disk, no real personal data |
| `alembic/versions/` | Two revisions: the initial six-table schema, then `chat_messages.kind` |
| `API.md` | The endpoint contract: request and response shapes, status codes, the SSE wire format, provider fallback behaviour |
| `render.yaml` | Render Blueprint — Python 3.11.9, migrate-then-serve start command, `/health` health check, every secret `sync: false` |
| `Dockerfile` | The same service as a container, for any host that takes an image |
| `.python-version` | 3.11.9, kept in step with `PYTHON_VERSION` in `render.yaml` |

### Frontend

| File | Responsibility |
|---|---|
| `App.tsx` | React Router setup, global layout shell (sidebar + main), auth guard, and route-level code splitting via `lazy` |
| `lib/supabase.ts` | Single Supabase client instance used by auth store and service calls |
| `lib/navigation.ts` | Holds the router's navigate function so code outside React (the Axios interceptor) can redirect |
| `lib/preferences.ts` | Per-browser preferences in localStorage, e.g. the default analysis depth set in Settings |
| `lib/download.ts` | Saves a generated document as a text file via a Blob URL |
| `store/authStore.ts` | Holds Supabase session and user object. Handles login, logout, session restore, and the onboarding-skip flag |
| `store/chatStore.ts` | Holds the active chat: messages, current analysis, streaming state, and generated outputs |
| `store/chatListStore.ts` | Holds all user chats for sidebar rendering |
| `store/trackerStore.ts` | Holds all tracker entries. Updated when a new chat is created or status is changed |
| `store/toastStore.ts` | Toast queue with auto-dismiss. `pushToast` can be called from a store action with no component in the middle |
| `store/session.ts` | `endSession` — clears every store and every persisted key, so the next user starts clean |
| `store/sessionExpired.ts` | One place a 401 turns into sign-out, a toast, and a redirect, debounced against a burst of them |
| `hooks/useStream.ts` | Reads the SSE response with a `fetch` reader, splits frames, appends tokens to the chat store in real time |
| `hooks/useAuth.ts` | Reads auth store, provides redirect helpers and auth status booleans |
| `hooks/useProfileSectionEditor.ts` | Debounces a section's edits into one `PATCH /profile` and drives the section's save status |
| `services/api.ts` | Single Axios instance. Reads JWT from auth store and injects it as Authorization header on every request |
| `types/index.ts` | All shared interfaces: Profile, WorkExperience, JobChat, ChatMessage, Analysis, TrackerEntry, GeneratedOutput |
| `components/chat/AnalysisTypeSelector.tsx` | Renders Quick Snapshot vs Detailed Breakdown choice before first analysis is run |
| `components/chat/AnalysisCard.tsx` | Renders a completed analysis — one card for both depths, with the detailed skill table expandable |
| `components/chat/OutputActions.tsx` | The explicit buttons for resume, cover letter, and answer, alongside asking for one in chat |
| `components/chat/OutputsPanel.tsx` | Lists what has been generated in this chat and offers each as a download |
| `components/profile/ProfileGapNudge.tsx` | Inline component that surfaces a gap suggestion and includes a dismiss action |
| `components/profile/ProfileCompleteness.tsx` | Turns the gap list into a single completeness score at the top of the profile |
| `components/common/ErrorBoundary.tsx` | Catches a render-time crash and shows a recoverable screen instead of a blank page |
| `components/common/BackendStatus.tsx` | Polls `GET /health` and renders the connection pill |
| `components/tracker/statuses.ts` | Status labels and display order, shared by the filters, the picker, and the row badge |

---

## Notes

- No audio or file storage. Resumes are parsed in memory on upload and the raw file is discarded. Only the extracted structured profile data is saved to the database.
- The `lib/` directory holds the Supabase client and any other third-party SDK instances that need to be initialized once and imported wherever needed.
- The Zustand stores that need to survive a page reload — `profileStore`, `chatListStore`, `trackerStore` — use the `persist` middleware with localStorage as the storage adapter. The auth store does not use persist: Supabase handles session restoration natively. Neither do `chatStore`, `toastStore`, or `uiStore` — a chat is always rebuilt from the server, and a toast or an open drawer that survived a reload would be a bug, not a restored preference.
- The `utils/context_builder.py` is the most critical backend utility. It determines what the AI sees in every call. Keep it well-tested and well-documented.
- Streaming responses use Server-Sent Events (SSE) from FastAPI. `EventSource` cannot send an `Authorization` header or a POST body, so `useStream` consumes the stream with `fetch` and a `ReadableStream` reader rather than `EventSource`.
- The root `supabase/` folder is the Supabase CLI project: `config.toml` describes the local Docker stack that `npx supabase start` brings up. No SQL migrations live there — Alembic owns the schema.
