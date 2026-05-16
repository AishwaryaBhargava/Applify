# Applify
### Your Job Application Co-Pilot
**Development Pipeline — V2.0**

---

## Phase Summary

| Phase | Title |
|---|---|
| Phase 0 | Setup and Prerequisites |
| Phase 1 | Project Scaffolding |
| Phase 2 | Database Setup |
| Phase 3 | Authentication |
| Phase 4 | Onboarding and Resume Parsing |
| Phase 5 | Profile — Enrichment and Gap Detection |
| Phase 6 | Job Chats and JD Analysis |
| Phase 7 | AI Outputs — Resume, Cover Letter, Answers |
| Phase 8 | Job Tracker |
| Phase 9 | Polish and Deploy |

> Each phase includes: Goal, What We Do (with checkboxes), Acceptance Criteria, Outcome, Notes / References, Testing, and Evaluation.

---

## Phase 0: Setup and Prerequisites

| | |
|---|---|
| **Phase** | 0 of 9 |
| **Estimated Effort** | 0.5 day |
| **Dependencies** | None |

### Goal:
Prepare the development environment, acquire all necessary credentials, and confirm Azure AI Foundry and Groq are responding before any application code is written.

### What we do:

**Accounts and Credentials:**
- [ ] Create Azure account at portal.azure.com if not already present
- [ ] Create an Azure AI Foundry resource and note the endpoint URL
- [ ] Deploy GPT-4o model in Azure AI Foundry and note the deployment name
- [ ] Generate and securely store the Azure API key
- [ ] Create Groq account at console.groq.com and generate an API key
- [ ] Create Supabase project at supabase.com and note the database URL, anon key, and JWT secret
- [ ] Create Vercel account (frontend deploy)
- [ ] Create Render account (backend deploy)

**Local Environment:**
- [ ] Verify Node.js v18+ is installed
- [ ] Verify Python 3.11+ and pip are installed
- [ ] Verify git is configured with correct user details

**Verification:**
- [ ] Run a standalone Python script that calls Groq with a test message and prints the response
- [ ] Run a standalone Python script that calls Azure GPT-4o with a test message and prints the response
- [ ] Connect to Supabase from a local Python script and confirm the connection is successful

**Documentation:**
- [ ] Finalize and store all 5 project documents (Problem Statement, Tech Stack, Folder Structure, Pipeline, README)

### Acceptance Criteria:
- Azure AI Foundry resource is active with GPT-4o deployment confirmed
- A test API call to Azure GPT-4o returns a valid response
- A test API call to Groq returns a valid chat completion response
- Supabase project is active and connection string is verified
- All credentials are stored securely and not committed to git
- Vercel and Render accounts are accessible

### Outcome:
A fully prepared environment with all services verified before a single line of application code is written.

### Notes / References:
- Never commit the actual `.env` file — only `.env.example`
- The Azure OpenAI SDK (`openai` Python package) is used for GPT-4o calls through Azure AI Foundry
- The `groq` Python package is used for Groq chat completions

### Testing:
- Groq test script returns a valid response with no auth errors
- Azure GPT-4o test script returns a valid response with no auth errors
- Supabase connection script connects and prints the database version with no errors

### Evaluation:
- All three service calls succeed with the stored credentials
- Any developer can reproduce the test calls by following the README instructions

---

## Phase 1: Project Scaffolding

| | |
|---|---|
| **Phase** | 1 of 9 |
| **Estimated Effort** | 1 day |
| **Dependencies** | Phase 0 complete |

### Goal:
Stand up a working frontend and backend skeleton with the full folder structure in place, routing configured, CORS enabled, and a verified end-to-end connection between frontend and backend.

### What we do:

**Project Structure:**
- [ ] Create root folder `applify/` with `backend/` and `frontend/` subdirectories
- [ ] Initialize git repository at root level
- [ ] Create `.gitignore` at root, backend, and frontend levels
- [ ] Create `.env` and `.env.example` at all levels with placeholder values

**Backend:**
- [ ] Create Python virtual environment inside `backend/`
- [ ] Install dependencies: fastapi, uvicorn, openai, groq, python-multipart, pydantic, pydantic-settings, python-dotenv, sqlalchemy, psycopg2-binary, alembic, pdfplumber, python-docx
- [ ] Generate `requirements.txt`
- [ ] Implement `core/config.py` with Settings class loading all env vars
- [ ] Implement `main.py` with FastAPI app, CORS middleware, and router registration
- [ ] Implement `GET /health` route returning `{ "status": "ok" }`
- [ ] Create all route, schema, service, model, and utility files as empty skeletons
- [ ] Verify backend runs locally on http://localhost:8000

**Frontend:**
- [ ] Initialize React + Vite + TypeScript project inside `frontend/`
- [ ] Install and configure Tailwind CSS
- [ ] Install dependencies: zustand, axios, lucide-react, react-markdown, react-router-dom, @supabase/supabase-js
- [ ] Create `lib/supabase.ts` with Supabase client instance
- [ ] Create all Zustand store skeleton files with initial state and no logic
- [ ] Create placeholder component and page files as empty shells with no logic
- [ ] Create `services/api.ts` with Axios instance using `VITE_API_URL`
- [ ] Create `types/index.ts` with all shared interfaces: Profile, WorkExperience, JobChat, ChatMessage, Analysis, TrackerEntry, GeneratedOutput
- [ ] Set up React Router in `App.tsx` with routes for all pages: Login, Signup, Onboarding, Chat, Profile, Tracker
- [ ] Build static layout shell: sidebar + main area (no logic, structure only)
- [ ] Verify frontend runs locally on http://localhost:5173

**Integration:**
- [ ] Frontend calls `GET /health` and renders the response on screen
- [ ] Confirm no CORS errors in browser console

### Acceptance Criteria:
- Backend runs on localhost:8000 and `GET /health` returns `{ "status": "ok" }`
- Frontend runs on localhost:5173 with sidebar and main area visible
- Frontend successfully fetches `/health` with no CORS errors
- All skeleton files exist with no TypeScript or Python import errors
- Folder structure matches the finalized structure document exactly

### Outcome:
A complete skeleton application where both frontend and backend are running, connected, and ready for feature development.

### Notes / References:
- Do not add any business logic in this phase — skeletons only
- All page routes should render a placeholder heading so navigation is testable from the start

### Testing:
- Navigate to localhost:5173, confirm layout shell renders with no console errors
- `curl http://localhost:8000/health`, confirm `{ "status": "ok" }`
- Open browser dev tools, confirm `/health` call returns 200 with no CORS error
- Import each store file in a test component and confirm no TypeScript errors

### Evaluation:
- Zero import errors across all skeleton files
- Zero CORS errors in browser console
- A new developer can clone the repo and reach this state in under 15 minutes

---

## Phase 2: Database Setup

| | |
|---|---|
| **Phase** | 2 of 9 |
| **Estimated Effort** | 1 day |
| **Dependencies** | Phase 1 complete |

### Goal:
Define the full database schema using SQLAlchemy models, wire the database connection into FastAPI, and run the first Alembic migration so every subsequent phase can read and write data without touching database setup again.

### What we do:

**Supabase:**
- [ ] Copy the database connection string (Session mode, port 5432) from Project Settings and add to backend `.env` as `SUPABASE_DATABASE_URL`
- [ ] Copy the JWT secret from Project Settings and add as `SUPABASE_JWT_SECRET`
- [ ] Confirm the connection string works from a local Python script

**Backend: Database connection:**
- [ ] Add `SUPABASE_DATABASE_URL` and `SUPABASE_JWT_SECRET` to `core/config.py`
- [ ] Implement `data/database.py` with SQLAlchemy engine, SessionLocal, and Base
- [ ] Implement `data/deps.py` with `get_db` dependency and `get_current_user` dependency that decodes the Supabase JWT and returns the user id

**Backend: Models:**
- [ ] Implement `models/profile.py` — user_id, raw_text, parsed_json, created_at, updated_at
- [ ] Implement `models/job_chat.py` — id, user_id, title, company, jd_text, analysis_type, created_at
- [ ] Implement `models/chat_message.py` — id, chat_id, role, content, created_at
- [ ] Implement `models/analysis.py` — id, chat_id, type, fit_score, strengths, gaps, verdict, full_json, created_at
- [ ] Implement `models/tracker_entry.py` — id, chat_id, user_id, status, resume_type, created_at, updated_at
- [ ] Implement `models/generated_output.py` — id, chat_id, output_type, content, created_at
- [ ] Import all models in `models/__init__.py`

**Alembic:**
- [ ] Initialize Alembic inside `backend/`
- [ ] Configure `alembic.ini` and `alembic/env.py` to use `SUPABASE_DATABASE_URL` and import all models
- [ ] Generate initial migration: `alembic revision --autogenerate -m "initial schema"`
- [ ] Run migration: `alembic upgrade head`
- [ ] Confirm all 6 tables are created in Supabase dashboard

### Acceptance Criteria:
- All 6 SQLAlchemy models are implemented and importable with no errors
- `alembic upgrade head` runs successfully with no errors
- All 6 tables are visible in the Supabase table editor with correct columns and types
- `get_db` and `get_current_user` dependencies are injectable with no errors

### Outcome:
A fully wired database layer where all tables exist and are accessible from FastAPI, ready for every subsequent phase.

### Notes / References:
- Never modify the schema manually in Supabase — always go through an Alembic migration
- `get_current_user` reads the Authorization header, decodes the JWT using `SUPABASE_JWT_SECRET`, and returns the user_id. This dependency is applied to every protected route.

### Testing:
- Write a test script that inserts a dummy row into each table and reads it back
- Confirm `get_current_user` correctly rejects a request with no token and accepts a valid one
- Run `alembic history` and confirm one clean initial migration is listed

### Evaluation:
- All 6 tables exist with correct columns and types
- Alembic migration history shows one clean initial migration
- No manual schema changes in Supabase dashboard

---

## Phase 3: Authentication

| | |
|---|---|
| **Phase** | 3 of 9 |
| **Estimated Effort** | 1 day |
| **Dependencies** | Phase 2 complete |

### Goal:
Implement email and Google authentication via Supabase Auth, protect all backend routes with JWT verification, and confirm the full auth flow works end-to-end before any product features are built on top.

### What we do:

**Backend: Auth middleware:**
- [ ] Implement `utils/auth.py` with `decode_jwt(token)` helper using `SUPABASE_JWT_SECRET`
- [ ] Implement `get_current_user` dependency fully in `data/deps.py` — reads Authorization header, decodes token, returns user_id, raises 401 on invalid or missing token
- [ ] Apply `get_current_user` as a dependency to all routes except `GET /health`
- [ ] Confirm all protected routes return 401 with no token and 200 with a valid token

**Frontend: Auth pages:**
- [ ] Implement `Login.tsx` with email + password form and Google OAuth button
- [ ] Implement `Signup.tsx` with email + password form and Google OAuth button
- [ ] Implement `authStore.ts` — holds Supabase session and user object, handles login, logout, and session restore on app load
- [ ] Implement `useAuth.ts` hook with isAuthenticated, isLoading, and redirect helpers
- [ ] Add auth guard to `App.tsx` — unauthenticated users are redirected to Login on any protected route
- [ ] After successful login, check if profile exists in the database. If not, redirect to Onboarding. If yes, redirect to Chat.
- [ ] Implement logout — clears Supabase session and auth store, redirects to Login

**Supabase Auth configuration:**
- [ ] Enable Email + Password provider in Supabase Auth dashboard
- [ ] Enable Google OAuth provider in Supabase Auth dashboard (requires Google Cloud OAuth client)
- [ ] Set redirect URLs for local and production environments

### Acceptance Criteria:
- User can sign up with email and password and is redirected correctly
- User can log in with Google OAuth and is redirected correctly based on profile existence
- JWT is verified on every protected backend route — invalid token returns 401, valid token returns 200
- Auth state persists across page reloads via Supabase session restoration
- Logout clears all session data and redirects to Login

### Outcome:
A fully authenticated app where every route is protected and the auth flow works correctly end-to-end.

### Notes / References:
- Supabase handles Google OAuth configuration. The frontend uses the Supabase client SDK to initiate the OAuth flow.
- The backend never calls Supabase Auth directly — it only decodes and verifies the JWT using the JWT secret.
- The Supabase client on the frontend manages the session cookie automatically via `onAuthStateChange`.

### Testing:
- Sign up with a new email, confirm user is created in Supabase Auth dashboard
- Log in with the same email, confirm redirect to Onboarding (no profile yet)
- Log in with Google OAuth, confirm redirect works
- Make a request to a protected route with no token, confirm 401
- Make a request with a valid token, confirm 200
- Refresh the page, confirm the user remains logged in

### Evaluation:
- Auth flow completes end-to-end with no errors on both email and Google paths
- 401 is returned reliably on every protected route with an invalid or missing token
- Session restores correctly on page reload with no flicker or redirect loop

---

## Phase 4: Onboarding and Resume Parsing

| | |
|---|---|
| **Phase** | 4 of 9 |
| **Estimated Effort** | 1.5 days |
| **Dependencies** | Phase 3 complete |

### Goal:
Build the onboarding flow where new users upload their resume, the system parses it into a structured profile, and the parsed data is saved to the database ready for all downstream AI features.

### What we do:

**Backend: Resume parser:**
- [ ] Implement `services/resume_parser.py` with `parse_resume(file_bytes, file_type)` function
- [ ] PDF path: use `pdfplumber` to extract raw text from all pages
- [ ] DOCX path: use `python-docx` to extract paragraphs and table text
- [ ] Post-extraction: pass raw text to Groq with a structured extraction prompt that returns JSON with sections: work_experience, education, skills, certifications, projects, achievements
- [ ] Save both `raw_text` (full extracted string) and `parsed_json` (structured dict) to the profile table

**Backend: Profile upload route:**
- [ ] Implement `POST /profile/upload` — accepts multipart file upload (PDF or DOCX only), calls `resume_parser.py`, saves result to profile table, returns the parsed profile JSON
- [ ] Implement `GET /profile` — returns the current user's full profile JSON
- [ ] Reject non-PDF and non-DOCX files with a clear 400 error

**Frontend: Onboarding page:**
- [ ] Implement `Onboarding.tsx` — a focused single-purpose page for first-time users
- [ ] Implement `ResumeUpload.tsx` component with drag-and-drop area and file picker (PDF and DOCX only, max 10MB)
- [ ] On file selection, show file name and a confirm upload button
- [ ] On upload, call `POST /profile/upload` and show parsing progress: Uploading → Parsing → Saving
- [ ] On success, redirect to Profile page so user can review parsed data
- [ ] Implement a skip option — redirects to Chat with a persistent profile nudge banner

**Frontend: Onboarding routing:**
- [ ] After login, check `GET /profile`. If profile exists, redirect to Chat. If not, redirect to Onboarding.
- [ ] If user skips onboarding, mark skip in authStore so the nudge banner shows on Chat

### Acceptance Criteria:
- New user after signup lands on Onboarding
- Resume upload accepts PDF and DOCX, rejects all other file types with a clear error message
- Parsing progress states render correctly: Uploading, Parsing, Saving
- Parsed profile is saved to the database with correct structure across all sections
- On success, user is redirected to Profile page with parsed data visible
- Skip option redirects to Chat with nudge banner visible

### Outcome:
A smooth first-run experience where users go from signup to a structured profile in under 3 minutes.

### Notes / References:
- The quality of resume parsing directly determines the quality of every AI output downstream. The Groq extraction prompt is the most important thing to get right in this phase.
- Raw text is saved alongside parsed JSON so the extraction can be re-run if the prompt is improved later without re-uploading the file.
- Resume files are never stored — only the extracted text and parsed JSON are saved.

### Testing:
- Upload a PDF resume, confirm parsed JSON contains correct work experience, skills, and education
- Upload a DOCX resume, confirm the same
- Upload a non-PDF/DOCX file (e.g. PNG), confirm 400 error
- Skip onboarding, confirm nudge banner appears on Chat page
- Return to app after skipping, confirm redirect goes to Chat (not Onboarding again)

### Evaluation:
- Work experience, education, and skills parse correctly from a real resume with no manual cleanup required
- Parsing completes in under 10 seconds for a standard 1-2 page resume
- Parsed JSON is correctly structured and saved to the database

---

## Phase 5: Profile — Enrichment and Gap Detection

| | |
|---|---|
| **Phase** | 5 of 9 |
| **Estimated Effort** | 1.5 days |
| **Dependencies** | Phase 4 complete |

### Goal:
Build the full profile page where users can review, edit, and manually enrich their parsed data. Implement AI-powered gap detection that nudges users to fill in missing or thin sections — but backs off if dismissed.

### What we do:

**Backend: Profile routes:**
- [ ] Implement `PATCH /profile` — accepts partial profile update as JSON, merges with existing parsed_json, saves to database, returns updated profile
- [ ] Implement `GET /profile/gaps` — analyzes the current profile JSON and returns a list of thin or missing sections with a suggested nudge message for each
- [ ] Implement `profile_service.py` with `detect_gaps(profile_json)` — checks each section for completeness and returns structured gap suggestions

**Frontend: Profile page:**
- [ ] Implement `Profile.tsx` — renders all profile sections: Experience, Education, Skills, Certifications, Projects, Achievements
- [ ] Implement `ProfileSection.tsx` — reusable collapsible section card with an edit toggle button
- [ ] Implement `ProfileField.tsx` — inline editable text field that saves on blur via `PATCH /profile`
- [ ] Implement `ProfileGapNudge.tsx` — soft suggestion banner for thin sections with a dismiss button
- [ ] On page load, fetch profile from `GET /profile` and gap suggestions from `GET /profile/gaps`
- [ ] Render gap nudge banners for missing or thin sections
- [ ] Dismissed nudge IDs are stored in localStorage — dismissed nudges do not reappear on reload
- [ ] If user dismisses all nudges, no further nudging happens until profile is next updated

**Frontend: Profile store:**
- [ ] Implement `profileStore.ts` fully — profile data, loading state, update action that calls `PATCH /profile` and updates local state

### Acceptance Criteria:
- All parsed profile sections render correctly in the profile page
- User can edit any field inline and changes persist to the database on blur
- Gap nudges appear for missing or thin sections and dismiss correctly
- Dismissed nudges do not reappear after page reload
- Profile page loads in under 2 seconds

### Outcome:
A rich, fully editable profile that gives the AI everything it needs to produce accurate analysis and tailored outputs in every subsequent phase.

### Notes / References:
- Gap detection runs on the backend so the logic is consistent. The frontend only renders the result.
- The AI in later phases pulls from `parsed_json` in the profile table. The richer this data, the better every analysis and output will be.

### Testing:
- Upload a resume with no certifications section, confirm the certifications gap nudge appears
- Edit a work experience field, reload the page, confirm the edit persisted
- Dismiss a nudge, reload the page, confirm it does not reappear
- Add a new skill manually, confirm it saves and appears correctly

### Evaluation:
- All edits persist correctly to the database on first attempt
- Gap detection identifies missing sections accurately on a real profile
- No nudge re-appears after being dismissed

---

## Phase 6: Job Chats and JD Analysis

| | |
|---|---|
| **Phase** | 6 of 9 |
| **Estimated Effort** | 2 days |
| **Dependencies** | Phase 5 complete |

### Goal:
Build the core product loop: create a job chat, paste a JD, choose analysis type, receive the analysis, and continue the conversation. This is the heart of Applify.

### What we do:

**Backend: Chat routes:**
- [ ] Implement `POST /chats` — creates a new chat with title, company, and JD text. Auto-creates a corresponding tracker entry.
- [ ] Implement `GET /chats` — returns all chats for the current user ordered by created_at descending
- [ ] Implement `GET /chats/{id}` — returns a single chat with its messages and analysis
- [ ] Implement `DELETE /chats/{id}` — soft deletes a chat
- [ ] Implement `POST /chats/{id}/analyze` — accepts analysis type (quick or detailed), runs analysis, saves result, returns structured JSON
- [ ] Implement `POST /chats/{id}/messages` — accepts a user message, calls chat service, streams response via SSE
- [ ] Implement `GET /chats/{id}/messages` — returns full message history for a chat

**Backend: Analysis service:**
- [ ] Implement `analysis_service.py` with `run_quick_analysis(profile, jd_text)` using Groq
- [ ] Quick snapshot output: fit_score (0-100), strengths (list of 3), gaps (list of 3), verdict (one sentence)
- [ ] Implement `analysis_service.py` with `run_detailed_analysis(profile, jd_text)` using Azure GPT-4o
- [ ] Detailed breakdown output: skill-by-skill comparison, gap reasoning per skill with suggestions, overall fit score with narrative
- [ ] Both analysis types return structured JSON saved to the analysis table
- [ ] Analysis is loaded from the database on subsequent visits — never re-run automatically

**Backend: Chat service:**
- [ ] Implement `chat_service.py` — builds AI context from profile + JD + chat history via `context_builder.py`, calls Groq, streams response via SSE
- [ ] After analysis is complete, the first AI message proactively suggests a next step (e.g. "Want me to tailor your resume for this role?")
- [ ] If user ignores or redirects, the AI backs off and waits for the user to drive
- [ ] Implement intent detection in `chat_service.py` — if the user message is requesting a resume, cover letter, or answer, route to `output_service.py` instead of chat

**Backend: Context builder:**
- [ ] Implement `utils/context_builder.py` — assembles profile summary + JD text + last N messages into a single context string
- [ ] Apply sliding window: if context exceeds 4000 words, truncate oldest messages first, always keeping profile and JD in context

**Frontend: Chat page:**
- [ ] Implement `Chat.tsx` — full chat page with sidebar chat list, new chat creation, and message thread
- [ ] Implement `NewChatButton.tsx` — opens a modal to enter job title, company, and paste JD text
- [ ] Implement `AnalysisTypeSelector.tsx` — renders after JD is submitted, before analysis runs. Quick Snapshot vs Detailed Breakdown.
- [ ] Implement `ChatThread.tsx` — scrollable message thread with auto-scroll to latest message
- [ ] Implement `ChatMessage.tsx` — user and assistant message bubbles with markdown rendering
- [ ] Implement `ChatInput.tsx` — text input with send button, disabled during streaming
- [ ] Implement `useStream.ts` hook — connects to SSE endpoint, appends streaming tokens to chatStore in real time
- [ ] Implement `chatListStore.ts` — fetches and holds all chats for sidebar rendering
- [ ] On new chat creation, add entry to chatListStore and trackerStore immediately

### Acceptance Criteria:
- User can create a new chat, paste a JD, choose analysis type, and receive a structured analysis
- Quick analysis returns structured result (fit score, strengths, gaps, verdict) in under 3 seconds
- Detailed analysis streams and completes within 15 seconds
- Chat continues after analysis with streaming AI responses
- First AI message after analysis proactively suggests a next step
- All messages are saved to the database and restored correctly on page reload
- New chat auto-creates a tracker entry

### Outcome:
The core product loop is complete. A user can go from a job description to a full fit analysis and continue the conversation, all grounded in their persistent profile.

### Notes / References:
- Analysis results are saved immediately on completion. If the user refreshes, analysis is loaded from the database — never re-run.
- Groq is used for quick analysis and chat because speed matters for conversational feel. Azure GPT-4o is used for detailed analysis because quality and depth matter more.
- The proactive suggestion after analysis is a single message. The AI does not repeat it if ignored.

### Testing:
- Create a new chat with a real JD, run quick analysis, confirm fit score and strengths/gaps are grounded in the profile
- Create a new chat, run detailed analysis, confirm skill-by-skill breakdown is accurate and relevant
- Send 5 messages in a chat, reload the page, confirm all messages are restored
- Confirm tracker entry is created automatically when a new chat is started
- Disconnect mid-stream, confirm the partial response is shown and a retry is available

### Evaluation:
- Quick analysis first token arrives in under 2 seconds
- Analysis content is grounded in the user's profile — not generic placeholder text
- Zero dropped tokens during streaming on a stable connection

---

## Phase 7: AI Outputs — Resume, Cover Letter, Answers

| | |
|---|---|
| **Phase** | 7 of 9 |
| **Estimated Effort** | 1.5 days |
| **Dependencies** | Phase 6 complete |

### Goal:
Implement on-demand AI output generation: tailored resume, cover letter, and application question answers. All outputs are generated only when the user asks, never automatically.

### What we do:

**Backend: Output routes:**
- [ ] Implement `POST /chats/{id}/outputs` — accepts output_type (resume, cover_letter, answer) and optional user_context string
- [ ] Route to the correct function in `output_service.py` based on output_type
- [ ] Stream response via SSE
- [ ] On completion, save the full output content to the `generated_outputs` table
- [ ] When output_type is resume, update the tracker entry resume_type to AI-Tailored

**Backend: Output service:**
- [ ] Implement `output_service.py` with `generate_resume(profile, jd_text, analysis)` using Azure GPT-4o
- [ ] Resume output: full tailored resume grounded strictly in profile data, formatted for the specific JD, with no fabricated experience
- [ ] Implement `output_service.py` with `generate_cover_letter(profile, jd_text, analysis, user_context)` using Azure GPT-4o
- [ ] Cover letter output: personalized to the company and role, grounded in profile, incorporates any user_context provided
- [ ] Implement `output_service.py` with `generate_answer(profile, jd_text, question, user_context)` using Azure GPT-4o
- [ ] Answer output: answers the specific application question drawing only from the profile, no fabrication
- [ ] All outputs stream token by token via SSE

**Frontend: Output rendering:**
- [ ] Generated outputs appear inline in the chat thread as formatted assistant messages with markdown rendering
- [ ] Each output message includes a Copy button that copies the full content to clipboard
- [ ] When a resume is generated, `chatStore` marks that chat as having an AI-tailored resume
- [ ] `trackerStore` updates resume_type to AI-Tailored for that chat immediately without a page reload

### Acceptance Criteria:
- User can ask for a tailored resume in chat and receive a streaming response grounded in their profile and the JD
- User can ask for a cover letter and receive a streaming response that references the company and role correctly
- User can paste an application question and receive an answer grounded in their profile
- All outputs are saved to the database on completion
- Tracker resume_type updates to AI-Tailored immediately when a resume is generated
- Copy button correctly copies the full output content

### Outcome:
The product delivers real, tangible value. A user walks away from each job chat with a tailored resume, cover letter, or application answer grounded in who they actually are.

### Notes / References:
- Outputs are triggered by user intent in the chat message, not by separate buttons. The intent detection in `chat_service.py` identifies the request and routes to `output_service.py`.
- The system prompt for all output generation explicitly prohibits fabricating experience, credentials, or skills not present in the profile.

### Testing:
- Ask for a resume in chat, confirm it streams, references the JD, and is saved to the database
- Ask for a cover letter with extra context ("mention my team leadership experience"), confirm the context is incorporated
- Paste a real application question, confirm the answer is grounded in the profile and relevant to the role
- Confirm tracker shows AI-Tailored after a resume is generated in that chat
- Copy the output, confirm clipboard content is correct and complete

### Evaluation:
- Generated resume includes profile content specifically relevant to the JD — not a generic resume
- Cover letter references the correct company name and role title
- First output token arrives within 3 seconds of the user's request

---

## Phase 8: Job Tracker

| | |
|---|---|
| **Phase** | 8 of 9 |
| **Estimated Effort** | 1 day |
| **Dependencies** | Phase 7 complete |

### Goal:
Build the full job tracker page where users can see all their applications in one place, track their status, see what type of resume was used, and navigate directly to any job chat.

### What we do:

**Backend: Tracker routes:**
- [ ] Implement `GET /tracker` — returns all tracker entries for the current user ordered by created_at descending
- [ ] Implement `PATCH /tracker/{chat_id}` — updates the status field for a specific tracker entry

**Frontend: Tracker page:**
- [ ] Implement `Tracker.tsx` — full tracker page with table, filter controls, and summary stats
- [ ] Implement `TrackerTable.tsx` — table with columns: job title, company, date added, analysis type, resume type, status
- [ ] Implement `TrackerRow.tsx` — single row with clickable job title (opens the chat), status picker, and resume type badge
- [ ] Implement `StatusPicker.tsx` — dropdown to update status: Not Applied, Applied, Interviewing, Offer, Rejected
- [ ] Filter pills at the top: All, Not Applied, Applied, Interviewing, Offer, Rejected
- [ ] Clicking a job title navigates directly to that chat
- [ ] Status updates call `PATCH /tracker/{chat_id}` and update `trackerStore` immediately without a full page reload
- [ ] Empty state renders when no chats have been created yet

**Frontend: Tracker store:**
- [ ] Implement `trackerStore.ts` fully — fetch all entries on app load, update on status change, add entry when a new chat is created

### Acceptance Criteria:
- All job chats appear in the tracker with correct metadata: title, company, date, analysis type, resume type, status
- User can update application status and it persists to the database on first attempt
- Filter pills correctly filter entries by status
- Clicking a job title opens the correct chat
- Resume type badge shows correctly: Unaltered or AI-Tailored
- Empty state renders correctly when no chats exist

### Outcome:
A clean, functional tracker that gives users a clear view of their entire application pipeline with no manual entry beyond status updates.

### Notes / References:
- The tracker entry is created automatically when a new chat is started (Phase 6). The user never manually adds entries.
- Resume type is the only field that auto-updates from the chat. All other fields except status are read-only in the tracker.

### Testing:
- Create 3 chats, open tracker, confirm all 3 appear with correct metadata
- Update status on one entry to Applied, reload the page, confirm it persisted
- Generate a resume in one chat, open tracker, confirm that entry shows AI-Tailored
- Filter by Interviewing, confirm only Interviewing entries show
- Click a job title in the tracker, confirm it opens the correct chat

### Evaluation:
- Tracker renders correctly with 20+ entries without performance degradation
- Status updates reflect in the UI immediately without a full page reload
- Resume type is always accurate across all entries

---

## Phase 9: Polish and Deploy

| | |
|---|---|
| **Phase** | 9 of 9 |
| **Estimated Effort** | 1.5 days |
| **Dependencies** | Phases 0 through 8 complete |

### Goal:
Add loading states, error handling, empty states, and UX polish across the entire app. Deploy frontend to Vercel, backend to Render, and confirm the full end-to-end flow works on live URLs.

### What we do:

**Error Handling:**
- [ ] Display a Toast notification on any API failure (analysis, chat, output generation, profile save)
- [ ] Handle network timeout gracefully — retry once, then show error with a retry button
- [ ] Handle Azure and Groq 429 rate limit errors with user-facing message: "Taking a moment, retrying..."
- [ ] Handle database connection errors with a clear 500 error message
- [ ] If streaming is interrupted mid-response, show partial response with a retry option

**Loading States:**
- [ ] Analysis: skeleton card while analysis is generating
- [ ] Chat: typing indicator from message send until first streaming token arrives
- [ ] Profile: skeleton sections while profile is loading
- [ ] Tracker: skeleton rows while tracker entries are loading
- [ ] Resume upload: progress stages rendering correctly (Uploading → Parsing → Saving)

**Empty States:**
- [ ] Chat list sidebar: empty state with a prompt to create the first job chat
- [ ] Tracker: empty state with a prompt to start applying
- [ ] Profile: empty state if user skipped onboarding, with a prompt to upload their resume

**UX Polish:**
- [ ] Confirm auto-scroll works reliably in chat thread during streaming
- [ ] Confirm all panels have correct overflow and scrollbar behavior
- [ ] Verify layout at 1280px, 1440px, and 1920px widths
- [ ] Verify sidebar collapses cleanly on narrow screens
- [ ] Dark mode: verify all CSS variables render correctly in dark theme

**Deploy: Frontend to Vercel:**
- [ ] Connect GitHub repo to Vercel
- [ ] Set `VITE_API_URL` to the Render backend URL in Vercel dashboard
- [ ] Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in Vercel dashboard
- [ ] Confirm build succeeds and app is accessible at a public Vercel URL

**Deploy: Backend to Render:**
- [ ] Create new Web Service on Render pointing to `backend/`
- [ ] Set start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] Set all environment variables in the Render dashboard
- [ ] Run `alembic upgrade head` and confirm all tables exist in Supabase
- [ ] Confirm `GET /health` returns `{ "status": "ok" }` on the live Render URL

**End-to-End Verification on Live URLs:**
- [ ] Sign up with a new account on the live URL, upload a resume, confirm profile parses correctly
- [ ] Create a new chat, run quick analysis, confirm result is grounded in the profile
- [ ] Create a new chat, run detailed analysis, confirm streaming result is accurate
- [ ] Ask for a tailored resume, confirm it generates and tracker updates to AI-Tailored
- [ ] Ask for a cover letter, confirm it references the correct company and role
- [ ] Open tracker, confirm all chats appear with correct data
- [ ] Update a status in the tracker, confirm it persists
- [ ] Open the app in a different browser with the same account, confirm all data is present

**README:**
- [ ] Update with live Vercel and Render URLs
- [ ] Add Supabase setup section
- [ ] Add Azure AI Foundry setup section
- [ ] Add Groq setup section
- [ ] Add Prompt Strategy section
- [ ] Add Tradeoffs section

### Acceptance Criteria:
- Frontend is live at a public Vercel URL
- Backend is live at a public Render URL with `/health` returning `{ "status": "ok" }`
- Supabase database is reachable from the live backend and all 6 tables are populated correctly
- All API errors show a user-facing Toast and do not crash the app
- Full end-to-end flow works on live URLs: signup, onboarding, profile, chat, analysis, output, tracker
- Data is consistent across different browsers with the same account
- README is complete with all setup sections

### Outcome:
A fully deployed, publicly accessible Applify beta with persistent data, working authentication, and the complete job application co-pilot loop functioning end-to-end.

### Notes / References:
- Render free tier has a cold start delay of approximately 30 seconds after inactivity. Acceptable for beta.
- Test the cross-browser data check explicitly — this is the proof that the database is working correctly in production, not just locally.
- Update `ALLOWED_ORIGINS` in backend `.env` to include the live Vercel URL before deploying.

### Testing:
- Complete a full end-to-end flow on the live URL: signup, upload, profile, chat, analysis, output, tracker
- Open the same account in a second browser, confirm all chats, profile, and tracker data are present
- Trigger each error state manually: disconnect network mid-stream, submit with an expired token
- Test on Chrome and Firefox
- Verify `GET /health` on the live Render URL returns 200

### Evaluation:
- Live app is fully functional with persistent data confirmed across browsers
- Quick analysis first token arrives in under 3 seconds on live URLs
- Zero 5xx errors during a clean end-to-end session on live URLs
- README is accurate enough that someone unfamiliar with the project can set it up locally in under 20 minutes
