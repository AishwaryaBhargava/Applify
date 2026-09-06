# Applify API

Base URL: `http://localhost:8000` in development. Interactive docs at `/docs`.

Every route except `GET /health` requires a Supabase access token:

```
Authorization: Bearer <supabase access token>
```

A missing, malformed, or expired token is `401` with a `WWW-Authenticate: Bearer`
header. Errors are FastAPI's standard shape, `{"detail": "..."}`, and request
validation failures are `422` with FastAPI's field-level detail list.

Ownership is enforced on every chat-scoped route by `user_id` **and**
`deleted_at IS NULL`. A chat that belongs to someone else, or one that has been
deleted, is a **404** -- never a 403, which would confirm it exists.

| Status | Meaning in this API |
|---|---|
| 401 | No usable token |
| 403 | A valid token, on a [private instance](#private-instances) whose allowlist does not name the caller |
| 404 | Not yours, deleted, or never existed |
| 409 | The user has no profile yet (`Upload your resume first`) |
| 413 | Request body over 11MB (`/profile/upload` refuses over 10MB with its own message) |
| 422 | Request body failed validation, or the chat has no JD |
| 501 | [`DELETE /account`](#delete-account) only: the server has no service role key, so nothing was deleted |
| 502 | The model provider was unreachable or returned nothing usable |
| 503 | Temporary: the database is unreachable, or a provider rate limit survived the fallback |
| 500 | Unexpected. The body is always `{"detail": "Something went wrong"}` — the traceback is logged, never returned |

`422` bodies carry a flattened sentence (`"title: String should have at least 1
character"`), not pydantic's nested list, because the frontend renders `detail`
straight into a toast. [`PATCH /profile`](#patch-profile) adds an `errors` list
alongside that sentence so the profile page can highlight the offending input;
it is the only endpoint that does, and the addition is purely additive.

The two `503`s are distinguished by their message: `Database unavailable, please
retry`, and a rate-limit message the frontend matches on to show "Taking a
moment, retrying..." rather than a hard error.

### Headers on every response

| Header | Value |
|---|---|
| `X-Request-ID` | A uuid per request, echoed from the request when one is sent, present on errors too, and stamped on every log line. Exposed to the browser via CORS |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Frame-Options` / `Content-Security-Policy` | `DENY` / `frame-ancestors 'none'` |

No HSTS: Render terminates TLS in front of the app.

### Provider fallback

Every model call names a preferred provider and falls back **once** to the other
one when the preferred provider is rate-limited, 5xx, or unreachable. Chat,
quick analysis, and resume extraction prefer Groq; the detailed analysis and all
generated documents prefer Azure GPT-4o. A `400`, `401`, `403`, or `422` from a
provider means our own request is wrong, and is never retried elsewhere.

Groq's free tier has a **daily** token cap. A daily cap ("tokens per day",
"TPD") skips the backoff retries entirely and fails over immediately -- waiting
cannot help before midnight. A per-minute limit is backed off first and only
then failed over.

So a `502` now means **both** providers failed, not one. Which provider actually
served a request is reported where it is free: `provider` on the SSE `done`
event, and `full_json._provider` on an analysis. Set `LLM_FALLBACK_ENABLED=false`
to disable failover, or `LLM_PREFER_AZURE_FOR_CHAT=true` to send chat to Azure
first.

---

## Health

### `GET /health`

Unauthenticated.

```json
{ "status": "ok", "db": "ok", "version": "5ce180c" }
```

| Field | Notes |
|---|---|
| `status` | Always `"ok"` while the process is answering. Liveness, not readiness |
| `db` | `"ok"` or `"error"` — a `SELECT 1` with a two-second ceiling that never raises |
| `version` | Short git sha of the running build, or `"dev"` |

The status code stays `200` even when `db` is `"error"`: a 5xx here would have
Render recycle a healthy instance over a database blip, and turn the frontend's
connection pill red for a backend that is up.

---

## Auth

### `POST /auth/verify`

Confirms the backend accepts the caller's token.

`200 {"user_id": "<uuid>"}`

---

## Profile

Implemented in Phases 4 and 5; summarised here because the chat routes depend on
a profile existing.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/profile/upload` | multipart `file`: PDF or DOCX, 10MB max. Parses in memory, stores `raw_text` + `parsed_json`. `400` unsupported format, `413` too large, `422` no text, `502` extraction model unreachable |
| `GET` | `/profile` | `404 "Profile not found"` drives the onboarding redirect |
| `PATCH` | `/profile` | Section-wise manual enrichment, validated strictly -- see below |
| `GET` | `/profile/gaps` | Rule-based nudges for missing or thin sections |
| `POST` | `/profile/import` | multipart `file`: a supplementary XLSX/CSV/DOCX/PDF/TXT/MD/JSON. Returns a **proposal and a diff**, saves nothing -- see [Supplementary import](#supplementary-import) |
| `POST` | `/profile/import/apply` | Writes the reviewed sections of a proposal |

`ProfileResponse`: `{user_id, raw_text, parsed_json, created_at, updated_at}`.

### `PATCH /profile`

Any subset of the profile sections, sent either at the top level (`{"skills":
[...]}`) or wrapped in `parsed_json`. A section that is present replaces that
section wholesale; an omitted section is untouched. Unknown keys are ignored
rather than 422-ing a whole edit.

**Two modes of coercion, on purpose.** `/profile/upload` is *lenient*: the
extraction model's output is cleaned up and whatever survives is kept, because a
half-read resume is still worth having and the user can fix the rest by hand. A
user edit is *strict*, because the opposite failure is worse -- a row that
vanishes on save with a `200` and no explanation is silent data loss. So the
rules below apply to `PATCH` only. A title-less role that arrived through
extraction is still accepted and stored; it just cannot be *typed* in.

Only the sections present in the request are validated, so a weak entry left
behind by an older extraction never blocks an unrelated edit to another section.

| Section | Required | Cleaned silently | Max lengths |
|---|---|---|---|
| `summary` | -- | Trimmed; empty becomes `null` | 2000 |
| `work_experience[]` | `title` **and** `company` | Blank highlights removed, de-duplicated | `title`, `company`, `location` 200; dates 100; `highlights` 20 items of 500 |
| `education[]` | `institution`, **plus** `degree` or `field` | -- | `institution`, `degree`, `field` 200; dates 100; `details` 2000 |
| `certifications[]` | `name` | -- | `name`, `issuer` 200; `year` 100 |
| `projects[]` | `name` | Blank technologies removed, de-duplicated | `name` 200; `description` 2000; `technologies` 60 each; `link` 500 |
| `skills[]` | -- | Blanks removed, duplicates folded case-insensitively | 60 each |
| `achievements[]` | -- | Blanks removed, duplicates folded case-insensitively | 500 each |
| `publications[]` | `title` | -- | `title` 500; `authors` 1000; `url` 500; `status`, `year` 100 |

The table above lists the fields that existed first. Every section has since
gained more -- see [Profile schema](#profile-schema) for the full list and the
limits that go with it.

An entry with **nothing** in it -- every field empty or absent -- is dropped
without an error. That is the row the editor added and the user never filled in,
and it is not a mistake. A **partially** filled entry missing a required field
is a `422`. Booleans do not count as content: a work entry where only the
"I work here now" toggle is set is still blank.

**Error shape.** Every section is checked before responding, so one save reports
every problem:

```json
{
  "detail": "work_experience[1]: company is required; education[0]: institution is required",
  "errors": [
    {"section": "work_experience", "index": 1, "field": "company", "message": "Company is required"},
    {"section": "education", "index": 0, "field": "institution", "message": "Institution is required"}
  ]
}
```

`detail` is the toast. `errors` is what the profile page highlights on: `index`
is the position in the **submitted** list, so it lines up with the editor's rows,
and is `null` for a section-level failure such as an over-long `summary`.

Validation runs on the incoming partial **before** the merge, so a `422` writes
nothing at all -- the stored profile is exactly what it was. A malformed body
(a string where a list belongs) is still pydantic's `422`, with the plain
`{"detail": "..."}` shape and no `errors` key.

---

## Chats

### `POST /chats`

Creates a job chat **and its tracker entry in the same transaction** -- the
tracker is never populated by hand.

Request:

```json
{
  "title": "Senior Backend Engineer",
  "company": "Kestrel Payments",
  "jd_text": "We need a backend engineer who writes Python..."
}
```

`title` is required (1-255 chars); `company` and `jd_text` are optional.
`analysis_type` is **not** accepted here -- it is set by `/analyze`.

Response `201`, `ChatResponse`:

```json
{
  "id": "3f1c...",
  "title": "Senior Backend Engineer",
  "company": "Kestrel Payments",
  "jd_text": "We need a backend engineer...",
  "analysis_type": null,
  "created_at": "2026-09-04T18:21:07.412Z",
  "has_analysis": false,
  "resume_type": "unaltered"
}
```

| Field | Notes |
|---|---|
| `analysis_type` | `null`, `"quick"`, or `"detailed"` |
| `has_analysis` | true once an analysis row exists for the chat |
| `resume_type` | from the chat's tracker entry: `"unaltered"` or `"tailored"` |

The new tracker entry starts as `status: "not_applied"`, `resume_type: "unaltered"`.

### `GET /chats`

`200 ChatResponse[]`, ordered `created_at` **descending**, excluding
soft-deleted chats and anything not owned by the caller. `has_analysis` and
`resume_type` are resolved in one query each, not per chat.

### `GET /chats/{chat_id}`

`200 ChatDetailResponse` -- everything the chat page needs after a reload:

```json
{
  "...": "all ChatResponse fields",
  "messages": [ /* MessageResponse[], oldest first */ ],
  "analysis": { /* AnalysisResponse or null */ }
}
```

`404` when the chat is not the caller's live chat.

### `DELETE /chats/{chat_id}`

Soft delete: stamps `deleted_at`. `204` with no body. The row and its tracker
entry stay in the database; the chat disappears from every read. `404` when the
chat is not the caller's.

---

## Analysis

### `POST /chats/{chat_id}/analyze?force=false`

Runs the profile-versus-JD analysis and persists it. **Non-streaming JSON** --
the frontend shows a skeleton card while it runs.

Request:

```json
{ "analysis_type": "quick" }
```

`analysis_type` is `"quick"` (Groq, seconds) or `"detailed"` (Azure GPT-4o,
deeper). `{"type": ...}` is accepted as an alias. Default `"quick"`.

Query parameter `force=true` re-runs the analysis and replaces the stored one.
Without it, **an existing analysis is returned as-is and no model call is made** --
opening a chat never re-runs an analysis, and the same profile against the same
JD never silently changes its score.

Response `200`, `AnalysisResponse`:

```json
{
  "id": "9a2b...",
  "chat_id": "3f1c...",
  "type": "quick",
  "fit_score": 74,
  "strengths": ["...", "...", "..."],
  "gaps": ["...", "...", "..."],
  "verdict": "Worth applying with a tailored resume.",
  "full_json": { },
  "created_at": "2026-09-04T18:24:55.001Z"
}
```

`fit_score`, `strengths`, `gaps`, and `verdict` are the summary and are present
for **both** depths, so one card renders either. `full_json` carries the
depth-specific detail, plus `_provider` (`"groq"` or `"azure"`) naming the model
that produced it -- underscored because it describes the request rather than the
candidate, and safe for a client to ignore:

* **quick** -- `{fit_score, strengths, gaps, verdict}`
* **detailed** --

```json
{
  "skills": [
    {
      "skill": "Kubernetes",
      "required_by_jd": true,
      "user_has": false,
      "evidence": "",
      "gap_reasoning": "The team runs its own clusters.",
      "suggestion": "Lead with the Docker work already on the profile."
    }
  ],
  "narrative": "A strong backend match held back by the infrastructure ask.",
  "fit_score": 68,
  "strengths": ["...", "...", "..."],
  "gaps": ["...", "...", "..."],
  "verdict": "Apply, but lead with the payments work.",
  "_provider": "azure"
}
```

A quick analysis normally reads `"_provider": "groq"`; `"azure"` means Groq was
rate-limited and Azure covered for it. Scores from two different models are not
comparable to the last point, which is the honest reason the field is exposed.

Side effects of a successful run, all in one transaction:

1. The analysis row is written (a forced re-run deletes the old one).
2. `job_chats.analysis_type` is set to the depth that ran.
3. **One** assistant `chat_messages` row is appended with `kind: "analysis"`,
   rendering the analysis as markdown and ending with a single proactive next
   step: *"Want me to tailor your resume for this role?"*

Errors:

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat |
| 409 | `Upload your resume first` -- no profile, or an empty one |
| 422 | The chat has no job description to analyse |
| 502 | The provider failed, or returned no JSON object |

Sloppy-but-recoverable model output is normalised rather than rejected: scores
are clamped into 0-100 (`"132"` becomes 100, `0.68` becomes 68), strengths and
gaps are de-duplicated and trimmed to three, and a detailed response with a
narrative but no verdict borrows the narrative's first sentence.

---

## Messages

### `GET /chats/{chat_id}/messages`

`200 MessageResponse[]`, ordered `created_at` **ascending**:

```json
{
  "id": "b41f...",
  "chat_id": "3f1c...",
  "role": "assistant",
  "content": "## Quick snapshot\n\n**Fit score: 74/100**...",
  "kind": "analysis",
  "created_at": "2026-09-04T18:24:55.001Z"
}
```

`role` is `"user"` or `"assistant"`. `kind` is `"chat"`, `"analysis"`,
`"resume"`, `"cover_letter"`, or `"answer"` -- what produced the message, so the
frontend can render each differently. User messages are always `"chat"`; the
detected intent is carried by the assistant message it produced.

`404` when the chat is not the caller's.

### `POST /chats/{chat_id}/messages`

Stores the user message and streams the assistant reply as **Server-Sent
Events**.

Request:

```json
{ "content": "How well do I fit this role?" }
```

Response `200`:

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

Errors are returned **before** the stream starts, because the status code is
fixed once the first byte is on the wire:

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat (nothing is written) |
| 422 | The message is empty or only whitespace |

#### SSE wire format

One JSON object per `data:` line, each event separated by a blank line. No
`event:` names -- the `type` field is the discriminator.

```
data: {"type":"start","message_id":"7c9e...","kind":"chat"}

data: {"type":"token","content":"Your "}

data: {"type":"token","content":"Python experience "}

data: {"type":"done","message_id":"7c9e...","content":"Your Python experience fits.","provider":"groq"}

```

| Event | Fields | Meaning |
|---|---|---|
| `start` | `message_id`, `kind` | The assistant message's id, chosen up front, and the detected intent. Render an empty bubble and stream into it. |
| `token` | `content` | One chunk. Append it; chunks are not line- or word-aligned. |
| `done` | `message_id`, `content`, `provider`, (`output_id`, `resume_type`) | The full text. The message is persisted at this point. `provider` is `"groq"` or `"azure"` -- which model actually served the reply, known only once the stream has run, which is why it cannot be on `start`. For an output `kind` the event also carries `output_id`, and for `resume` the tracker's new `resume_type`. The stream closes. |
| `error` | `message`, `message_id`, `partial`, `content` | Generation or persistence failed. `partial: true` means `content` did stream -- leave it on screen and offer a retry. `partial: false` means nothing was generated and nothing was stored. |

A database failure while saving the finished reply is reported as an `error`
event too, not as a truncated response: by then the `200` and every token are
already on the wire, so there is no status code left to turn into a `503`. The
event carries the full text with `partial: true` and a message saying the reply
could not be saved -- the one case where `partial: true` does **not** mean the
text was persisted.

The user message is persisted before the stream opens, so it survives a failure.
The assistant message is persisted on `done`, or on `error` when anything
streamed. A stream that yields no tokens at all is reported as an `error`, not
stored as an empty bubble.

#### Intent and the `kind` on `start`

Each user message is classified as `chat`, `resume`, `cover_letter`, or
`answer`, and that label is the `kind` on the `start` event and on the stored
assistant message.

Rules decide the clear cases with no model call:

| Rule | Result |
|---|---|
| A cover-letter phrase (`cover letter`, `covering letter`, `coverletter`, `motivation letter`) **plus** a generation verb (`write`, `draft`, `tailor`, `generate`, `rewrite`, ...) or a request marker (`can you`, `please`, `i need`, ...) | `cover_letter` |
| `resume` / `cv` **plus** a generation verb or request marker | `resume` |
| An answer phrase (`answer this question`, `how should i answer`, `help me answer`, `application question`, `what should i say`, ...) | `answer` |
| No output vocabulary at all | `chat` |
| Output vocabulary without a request (*"should I mention my resume gap?"*) | ambiguous -- one cheap Groq classification call decides |

Cover letter is checked before resume, so *"use my resume to write a cover
letter"* is a cover-letter request. If the classifier call fails, the message is
treated as `chat`: answering conversationally when a document was wanted is a
cheaper mistake than generating a document nobody asked for.

When the intent is not `chat`, generation is delegated to `output_service` and
the stream is an Azure GPT-4o document rather than a Groq chat reply. See
[Outputs](#outputs) for what the `done` event carries and what is persisted.

#### Model context

Chat replies come from Groq (`GROQ_MODEL`, streaming, `max_tokens` 2048), or
from Azure GPT-4o when Groq is rate-limited before the first token -- see
[Provider fallback](#provider-fallback). A stream that fails **after** tokens
have reached the client does *not* fail over: half a reply from each model would
contradict itself, so it is reported as an `error` with `partial: true`, exactly
like any other mid-stream failure. The context is assembled by
`utils/context_builder.build_messages`:

* a **system message** holding the persona, a compact profile summary rendered
  from `parsed_json`, the full JD, and the analysis summary when one exists;
* then the conversation history, oldest first.

Above 4000 words the sliding window drops the **oldest** history turns first.
Profile, JD, and analysis live in the system message and are structurally
un-droppable; the newest turn -- the one being answered -- is never dropped.

#### Consuming the stream

`EventSource` cannot send an `Authorization` header or a POST body, so use
`fetch` with a `ReadableStream` reader, split on `\n\n`, strip the leading
`data: `, and `JSON.parse` each frame.

---

## Outputs

Resume, cover letter, and application answers. All three come from Azure GPT-4o
(`AZURE_GPT4O_DEPLOYMENT`, streaming, `temperature` 0.4, `max_tokens` 3000), and
the initial call is wrapped in exponential backoff on 429 / 5xx.

There are two ways to ask for the same document:

* **by asking in chat** -- `POST /chats/{id}/messages` detects the intent and
  streams the document under the matching `kind`;
* **by pressing a button** -- `POST /chats/{id}/outputs` names the type outright.

They share one code path, so the SSE wire format is identical. The only
difference is that the button path writes the user turn it stands for, so the
thread reads the same either way.

### `POST /chats/{chat_id}/outputs`

Request:

```json
{ "output_type": "cover_letter", "user_context": "mention my team leadership" }
```

| Field | Notes |
|---|---|
| `output_type` | `"resume"`, `"cover_letter"`, or `"answer"`. Anything else is `422` |
| `user_context` | Optional, 8000 chars. A steer (*"keep it to one page"*), or -- for `answer` -- the application question itself |

Before the stream opens, the route stores a user message standing for the
button:

| `output_type` | Stored user message |
|---|---|
| `resume` | `Generate a tailored resume for this role` |
| `cover_letter` | `Write a cover letter for this role` |
| `answer` | `Answer this application question` |

`user_context`, when given, is appended after a colon -- so an `answer` request
is stored as `Answer this application question: <question>`, exactly the shape a
user typing it by hand would produce.

Response `200`: the **same SSE stream** as `POST /chats/{id}/messages`, with
`kind` fixed to the requested `output_type`:

```
data: {"type":"start","message_id":"7c9e...","kind":"resume"}

data: {"type":"token","content":"# Priya "}

data: {"type":"done","message_id":"7c9e...","content":"# Priya Raman\n...","provider":"azure","output_id":"1a2b...","resume_type":"tailored"}

```

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat (nothing is written) |
| 422 | `output_type` is missing or not one of the three |

#### What `done` carries for an output

| Field | Always | Meaning |
|---|---|---|
| `message_id` | yes | The assistant message, as announced on `start` |
| `content` | yes | The full document, markdown |
| `provider` | yes | Which model served it -- `"azure"` for every document kind |
| `output_id` | output kinds only | The new `generated_outputs` row, so the client can link to it without refetching |
| `resume_type` | `resume` only | The tracker's new value, `"tailored"`. Apply it to the tracker store directly -- no `GET /tracker` needed |

#### What is persisted

On `done`, one commit writes all of:

1. the assistant `chat_messages` row, under the streamed `message_id` and the
   output `kind`;
2. a `generated_outputs` row (`chat_id`, `output_type`, `content`);
3. for a resume, `tracker_entries.resume_type = "tailored"` for that chat.

A stream that fails part-way persists **only** the assistant message, with
`partial: true` on the `error` event. Half a resume is worth leaving on screen;
it is not filed in the user's outputs as a finished document, and it does not
flip the tracker.

#### Prompts

Every output type shares one grounding rule, stated in its system prompt: ground
each statement in the profile, never invent or embellish employers, titles,
dates, degrees, certifications, tools, or numbers, and output markdown only --
no preamble.

| Type | What the prompt asks for |
|---|---|
| `resume` | A full tailored resume: name and contact, then Summary, Experience, Skills, Education, Projects, Certifications as H2s, **omitting any section the profile has no content for**. Highlights are reordered and rephrased in the JD's own vocabulary while staying factually identical -- same scope, same numbers, same technologies |
| `cover_letter` | Three or four paragraphs addressed to the company and role named in the JD, tying two or three specific profile items to what the job asks for. The analysis's strengths, when one exists, decide which experiences lead. `user_context` is woven in as far as the profile supports it. Under 400 words unless the user asks otherwise |
| `answer` | The application question, answered in the first person from the profile. The question is extracted from the request -- everything after a marker such as *"answer this question:"*, or the whole message when there is no marker -- and stated on its own line in the prompt. 120-250 words unless the user asks for a length |

The model context is assembled by `output_service.build_output_prompt`: the
profile as **raw JSON** (not the chat summary -- a resume that drops a role
because the summary capped the list is a defect the user can see), the full JD,
the analysis summary when one exists, then the windowed conversation and the
triggering request. The budget is 6000 words; only history is ever trimmed.

### `GET /chats/{chat_id}/outputs`

`200 OutputResponse[]`, ordered `created_at` **descending**:

```json
{
  "id": "1a2b...",
  "chat_id": "3f1c...",
  "output_type": "resume",
  "content": "# Priya Raman\n\n## Summary\n...",
  "created_at": "2026-09-04T18:31:02.114Z"
}
```

`404` when the chat is not the caller's. A chat with no documents yet is `200
[]`, not a 404.

---

## Tracker

One tracker row per job chat, created automatically with the chat. The user
never adds one by hand, and the only field they edit is `status`.

A row is a view over three tables: `tracker_entries` holds `status` and
`resume_type`, the chat supplies the title, company, date and analysis type, and
the analysis supplies the fit score. Rows whose chat has been soft-deleted are
excluded -- the listing is driven by the user's live chats, so
`DELETE /chats/{id}` removes the application from the tracker without the
tracker knowing anything about `deleted_at`.

### `GET /tracker`

`200 TrackerEntry[]`, ordered `created_at` **descending**:

```json
{
  "id": "9d0e...",
  "chat_id": "3f1c...",
  "user_id": "5b7a...",
  "job_title": "Senior Backend Engineer",
  "title": "Senior Backend Engineer",
  "company": "Kestrel Payments",
  "date_added": "2026-09-01T12:00:00Z",
  "analysis_type": "detailed",
  "resume_type": "unaltered",
  "status": "not_applied",
  "fit_score": 74,
  "created_at": "2026-09-01T12:00:00Z",
  "updated_at": "2026-09-04T18:31:02.114Z"
}
```

| Field | Source | Notes |
|---|---|---|
| `id` | `tracker_entries` | The tracker row, not the chat |
| `chat_id` | `tracker_entries` | What the job title links to, and what `PATCH` is addressed by |
| `job_title` / `title` | chat | The same value under both names; `title` is the Phase 6 spelling the sidebar's optimistic entry uses |
| `company` | chat | Nullable |
| `date_added` | `job_chats.created_at` | When the user started this application |
| `analysis_type` | chat | `"quick"`, `"detailed"`, or `null` before an analysis |
| `resume_type` | `tracker_entries` | `"unaltered"`, or `"tailored"` once a resume was generated in the chat. Rendered as *Unaltered* / *AI-Tailored* |
| `status` | `tracker_entries` | `not_applied` \| `applied` \| `interviewing` \| `offer` \| `rejected` |
| `fit_score` | analysis | `0`-`100`, or `null` when the chat has no analysis |
| `created_at` / `updated_at` | `tracker_entries` | `updated_at` moves on every status change |

Empty list when the user has no live chats -- that is what drives the empty
state, not a 404.

### `PATCH /tracker/{chat_id}`

Addressed by **chat id**, because that is what the user is looking at and what
ownership is checked against.

```json
{ "status": "interviewing" }
```

`status` is the only field, and it is required. `resume_type` follows from
whether a resume was generated and is not settable by the client; every other
column is copied from the chat.

`200` returns the **full updated row**, in the shape above, so the tracker store
can replace the entry without a refetch.

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat, or has no tracker row |
| 422 | `status` is missing, or outside the five allowed values |


---

## Tracker: the application's own fields

A tracker row carries more than a status. Everything below describes the
*application* rather than the conversation, lives on `tracker_entries`, is
nullable, and is edited through `PATCH /tracker/{chat_id}`.

| Field | Type | Notes |
|---|---|---|
| `job_url` | string \| null | The posting. Must start with `http://` or `https://`; max 2000 chars |
| `location` | string \| null | Free text, max 255 |
| `salary` | string \| null | Free text on purpose -- `"$180-210k"`, `"GBP 75,000"`, `"competitive"`. Max 255 |
| `source` | string \| null | Where it was found: LinkedIn, referral, careers page. Max 255 |
| `applied_at` | timestamp \| null | When the application was sent. Stamped automatically, see below |
| `next_action` | string \| null | What the user has to do next, max 300 |
| `next_action_date` | date (`YYYY-MM-DD`) \| null | When that is due |
| `notes` | string \| null | Free text, max 5000 |
| `priority` | `low` \| `medium` \| `high` \| null | Null means "no opinion yet", not medium |

Two more fields are **derived per request** and are never stored, because both
are answers about *today*:

| Field | Type | Meaning |
|---|---|---|
| `days_since_applied` | int \| null | Whole days between `applied_at` and today (UTC). Null when the application has not been sent |
| `next_action_due` | bool | True when `next_action_date` is today or earlier. False when there is no date |

### The `applied_at` stamp

`status` is a current state and can be corrected in both directions. "When did I
send this" happened once. So:

* The first time `status` transitions **into** `applied` from anything else, and
  `applied_at` is still null, the server stamps it with `now()`.
* Moving back to `not_applied` -- or on to `interviewing`, `offer`, `rejected` --
  never changes it.
* A client may set `applied_at` explicitly (to back-date an application sent last
  week). An explicit value is never overwritten by the automatic stamp.

### `POST /chats` -- capturing three of them up front

`ChatCreateRequest` accepts three optional extras. They are written onto the
chat's auto-created tracker entry, not onto the chat, and they come back from
`GET /tracker` rather than from `ChatResponse`, which is unchanged.

```json
{
  "title": "Senior Backend Engineer",
  "company": "Kestrel Payments",
  "jd_text": "...",
  "job_url": "https://kestrel.example/jobs/42",
  "location": "Remote (UK)",
  "source": "LinkedIn"
}
```

`job_url` is validated exactly as the tracker validates it: `422` for anything
that is not http(s).

### `GET /tracker` -- filtering, search, and ordering

| Parameter | Values | Default |
|---|---|---|
| `status` | `not_applied` \| `applied` \| `interviewing` \| `offer` \| `rejected` | none (all rows) |
| `q` | free text, max 200 chars | none |
| `sort` | `created_at` \| `applied_at` \| `next_action_date` \| `fit_score` | `created_at` |

`q` is a case-insensitive substring match over **job title, company, and notes**
-- the three free-text fields a user would type into a search box. Filters
combine: `?q=engineer&status=rejected` applies both.

Ordering is newest/highest first for `created_at`, `applied_at` and `fit_score`.
`next_action_date` is the one exception and runs **ascending**: the follow-up due
today matters more than the one due next month. A row with no value for the
chosen key always sorts **last**, whichever direction applies -- an unscored
application is unanswered, not a zero.

An unknown `status` or `sort` is a `422`, not a silently empty table.

### `PATCH /tracker/{chat_id}` -- partial update

Accepts **any subset** of:

```json
{
  "status": "applied",
  "job_url": "https://kestrel.example/jobs/42",
  "location": "Remote (UK)",
  "salary": "GBP 75,000",
  "source": "Referral",
  "applied_at": "2026-08-20T09:00:00Z",
  "next_action": "Follow up with the recruiter",
  "next_action_date": "2026-09-12",
  "notes": "Referred by Priya.",
  "priority": "high"
}
```

A field that is **absent** is left alone. A field sent as **`null`** is cleared.
Whitespace-only text clears the field too. `resume_type` is still not settable by
the client -- it follows from whether a resume was generated in the chat.

`200` returns the full updated row, including the derived fields.

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat, or has no tracker row |
| 422 | Empty body; a `status` or `priority` outside its enum; a `job_url` that is not http(s); `notes` over 5000 or `next_action` over 300 characters; a date that is not ISO |

An empty body (`{}`) is a `422`. "Update nothing" is never what a client meant,
and accepting it would turn a frontend bug into a silent `200`.

---

## Keywords (ATS match)

Applicant tracking systems screen on words. This endpoint answers the question
worth asking before hitting *Apply*: of the things this posting asks for, which
ones does the candidate's own material actually say?

The feature is deliberately split in two.

* **Extraction is a model call.** Reading a JD and deciding that "own the CI/CD
  pipeline" is a *required* responsibility while "familiarity with Kafka is a
  plus" is a *preferred* tool is comprehension. It runs on **Azure GPT-4o**
  (temperature 0.1, 2048 tokens), and the result is cached on the chat.
* **Matching is deterministic.** Whether the profile says "PostgreSQL" is not a
  judgement call. It is normalised string work, and it is **re-run on every
  request** -- including the ones that reuse a cached extraction. Edit the
  profile, call again, and the score moves, with no model call and no way for it
  to drift on its own.

### `POST /chats/{chat_id}/keywords`

| Parameter | Values | Default |
|---|---|---|
| `force` | bool | `false` |

Without `force`, a stored keyword list is reused and only the match is
recomputed. With `?force=true` the job description is read again -- the only way
to spend a model call on a JD that has not changed.

When the chat has a generated resume, its **latest** resume is searched as a
second corpus, so a keyword the profile has but the tailored resume dropped
shows up as `in_profile: true, in_resume: false`.

`200`:

```json
{
  "match_percent": 62,
  "required_matched": 5,
  "required_total": 8,
  "preferred_matched": 3,
  "preferred_total": 5,
  "keywords": [
    {
      "keyword": "postgresql",
      "category": "tool",
      "importance": "required",
      "aliases": ["postgres"],
      "in_profile": true,
      "in_resume": true,
      "evidence": "Tuned PostgreSQL for a 4TB ledger."
    },
    {
      "keyword": "kubernetes",
      "category": "tool",
      "importance": "required",
      "aliases": ["k8s"],
      "in_profile": false,
      "in_resume": false,
      "evidence": null
    }
  ],
  "missing_required": ["kubernetes"],
  "generated_at": "2026-09-05T11:04:18.552Z",
  "provider": "azure"
}
```

| Field | Notes |
|---|---|
| `match_percent` | Weighted, `0`-`100`. `required` counts **2**, `preferred` counts **1**: `100 * (2R + P) / (2Rtotal + Ptotal)`, rounded. `0` when there are no keywords |
| `required_matched` / `required_total` | Counted against the **profile**, not the resume |
| `preferred_matched` / `preferred_total` | Same |
| `keywords[].category` | `skill` \| `tool` \| `qualification` \| `responsibility` \| `soft_skill` \| `domain` |
| `keywords[].importance` | `required` \| `preferred` |
| `keywords[].aliases` | Other spellings that counted -- the model's, plus the built-in table. Shown in the UI to explain a match |
| `keywords[].in_profile` | Whether the profile evidences it |
| `keywords[].in_resume` | `true`/`false` when the chat has a generated resume; **`null`** when it has none. Null is "not checked", not "the resume omits it" |
| `keywords[].evidence` | The first matching line of the candidate's own material, trimmed to 120 characters (ellipsis included). Null when nothing matched. Falls back to the resume's line when only the resume matched |
| `missing_required` | The `required` keywords with no evidence in the profile -- the actionable half |
| `provider` | Which provider *extracted* the keywords. The match itself is not a model call |

The extraction asks for 15-40 keywords, deduplicated, lowercase. A model that
returns an unknown category, a missing importance, a bare string, or the same
keyword under two spellings produces a slightly poorer match, never a 500;
entries with no keyword at all are dropped, and the list is capped at 40.

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's live chat |
| 409 | The user has no profile (`"Upload your resume first"`) |
| 422 | The chat has no job description |
| 502 | The extraction model is unreachable, or returned nothing usable |

### `GET /chats/{chat_id}`

Now also carries `keyword_match`: the exact object above, or `null` if the match
has never been run for this chat. Reopening a chat redraws the panel without a
second request and without re-running anything.

### Matching rules

Normalisation, applied identically to both sides of every comparison:

* lowercased; everything that is not a letter, digit, `+` or `#` becomes a space,
  so `CI/CD`, `ci-cd` and `ci cd` collapse together while `C++` and `C#` survive;
* plurals folded (`APIs` -> `api`), conservatively -- tokens of three characters
  or fewer are left alone, which is what keeps `aws`, `js` and `k8s` intact;
* matches are whole-phrase and space-bounded, so `java` never matches inside
  `javascript`.

On top of that, a built-in alias table. Each group matches in **both**
directions, and the model's own `aliases` are folded in alongside it:

| | |
|---|---|
| `postgres` | `postgresql`, `postgre sql`, `psql` |
| `mysql` | `my sql` |
| `mongo` | `mongodb` |
| `elasticsearch` | `elastic search` |
| `k8s` | `kubernetes` |
| `js` | `javascript` |
| `ts` | `typescript` |
| `ml` | `machine learning` |
| `ai` | `artificial intelligence` |
| `llm` | `large language model` |
| `nlp` | `natural language processing` |
| `gcp` | `google cloud`, `google cloud platform` |
| `aws` | `amazon web services` |
| `azure` | `microsoft azure` |
| `ci/cd` | `ci cd`, `cicd`, `continuous integration`, `continuous delivery`, `continuous deployment` |
| `react` | `react.js`, `reactjs` |
| `node` | `node.js`, `nodejs` |
| `next.js` | `nextjs` |
| `vue` | `vue.js`, `vuejs` |
| `angular` | `angular.js`, `angularjs` |
| `.net` | `dotnet`, `dot net` |
| `c#` | `c sharp`, `csharp` |
| `c++` | `cpp` |
| `rest` | `restful`, `rest api`, `restful api` |
| `graphql` | `graph ql` |
| `db` | `database` |
| `nosql` | `no sql` |
| `oop` | `object oriented programming` |
| `iac` | `infrastructure as code` |
| `etl` | `extract transform load` |
| `tdd` | `test driven development` |
| `sre` | `site reliability engineering` |
| `qa` | `quality assurance` |
| `ux` | `user experience` |
| `ui` | `user interface` |
| `saas` | `software as a service` |
| `bi` | `business intelligence` |
| `crm` | `customer relationship management` |
| `github actions` | `gh actions` |
| `frontend` | `front end` |
| `backend` | `back end` |
| `fullstack` | `full stack` |

`go`/`golang` and `cv`/`computer vision` are deliberately **not** in the table:
"go" and "cv" are ordinary words in a resume, and a false match is worse than a
missed one, because the user acts on this list by editing their resume.

The profile corpus is the whole stored profile, not a summary: every string in
`parsed_json`, including coursework, honours, publications, and project links,
so new profile fields are matched the day they are added.

---

## Export

Everything Applify generates is Markdown, and nobody applies for a job by pasting
Markdown into a form.

### `GET /chats/{chat_id}/outputs/{output_id}/export`

| Parameter | Values | Default |
|---|---|---|
| `format` | `docx` \| `md` | `docx` |

Returns the file itself, not JSON.

| Format | Content-Type |
|---|---|
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `md` | `text/markdown; charset=utf-8` |

Both are sent as an attachment:

```
Content-Disposition: attachment; filename="kestrel-payments-cover-letter.docx"
```

The filename is `<company>-<kind>.<ext>`, slugified: lowercased, accents folded
(`Zürich` -> `zurich`), everything else collapsed to hyphens. `cover_letter`
becomes `cover-letter`. The company falls back to the chat's job title, and then
to `applify`, so the name is never empty.

| Status | Cause |
|---|---|
| 404 | The chat is not the caller's, or the output does not belong to that chat |
| 422 | `format` is neither `docx` nor `md` |

The output is looked up *within* the caller's chat, so an output id lifted from
someone else's chat resolves to nothing and returns the same 404 a made-up id
would.

### What the DOCX looks like

Page: 0.75in margins all round, Calibri 11, single spacing.

| Markdown | Rendered as |
|---|---|
| `# Heading` | Word's `Title` style, 16pt bold, dark teal (`#114B5A`), hairline rule under |
| `## Heading` | 12pt bold, hairline rule under |
| `### Heading` and deeper | 11pt bold, no rule |
| `- item`, `* item`, `+ item` | `List Bullet` |
| `1. item` | `List Number` |
| `**bold**`, `__bold__` | bold run |
| `*italic*`, `_italic_` | italic run |
| `` `code` `` | plain text, backticks stripped |
| `[label](url)` | plain text `label (url)`; a bare link is not repeated |
| `---`, `***`, `___` | a blank paragraph, not a printed line |
| `> quote` | an ordinary paragraph |
| blank lines | dropped -- spacing comes from the style |

The `title` argument becomes the Word core property, so the file identifies
itself in a document library; it is never drawn on the page, because the document
already opens with the candidate's name.

Anything the renderer does not recognise falls through as literal text rather
than raising. A resume that renders one line as literal `**` is a blemish; a
resume that fails to export at all is a lost application.

---

## Profile schema

`parsed_json` carries **eight** sections: `summary`, `work_experience`,
`education`, `skills`, `certifications`, `projects`, `achievements`, and
`publications`. Every field is optional and every list defaults to empty, so a
profile stored before any of the fields below existed loads unchanged and simply
reports the new ones as `null` / `[]`. Nothing here was renamed or removed.

### `work_experience[]`

| Field | Type | Notes |
|---|---|---|
| `title`, `company`, `location` | string \| null | |
| `start_date`, `end_date` | string \| null | Free text, as written |
| `current` | boolean | |
| `highlights` | string[] | The role's bullets |
| `employment_type` | string \| null | **New.** "Full-time", "Internship", "Contract"... Free text: an enum would reject half the spellings people use |
| `awards` | string[] | **New.** Recognition tied to this role, kept out of `highlights` so a generated resume can lead with it |

### `education[]`

| Field | Type | Notes |
|---|---|---|
| `degree`, `institution`, `field` | string \| null | |
| `start_date`, `end_date`, `details` | string \| null | |
| `gpa` | string \| null | **New.** As written, with its scale: `"8.7/10"`, `"3.8/4.0"`, `"First Class"`. Never a number -- grading scales differ by country and a float loses the scale |
| `coursework` | string[] | **New.** Short course names |
| `honors` | string[] | **New.** Short honour names |

### `certifications[]`

| Field | Type | Notes |
|---|---|---|
| `name`, `issuer`, `year` | string \| null | |
| `expires` | string \| null | **New.** Free text, like every other date |
| `credential_url` | string \| null | **New.** |
| `description` | string \| null | **New.** |

### `projects[]`

| Field | Type | Notes |
|---|---|---|
| `name`, `description` | string \| null | |
| `technologies` | string[] | |
| `link` | string \| null | **Kept.** The single legacy URL. When it is absent it is filled with the first non-empty of `links.github`, `links.live`, `links.demo`, so a client written against the old shape never loses a URL a new writer supplied |
| `links` | object | **New.** `{github, live, demo}`, each string \| null. Three named slots rather than a list, because a resume renders source, a deployment, and a walkthrough differently |
| `start_date`, `end_date` | string \| null | **New.** |
| `highlights` | string[] | **New.** Key contributions and impact -- the project equivalent of a role's bullets |

### `publications[]` (new section)

| Field | Type | Notes |
|---|---|---|
| `title` | string \| null | **Required** under strict validation |
| `authors` | string \| null | One string, in the source's own order. Not a list: author order matters and citation styles differ, so splitting loses both |
| `url`, `status`, `year` | string \| null | `status` is "Published", "Under review", "Accepted", "Preprint"... |

`achievements` stays a `string[]`. The importer formats a structured achievement
as `"Name -- Organization (Date): description"`, dropping any part the source
does not state.

### Validation of the new fields

The `PATCH /profile` rules extend the same way: required fields make a partially
filled entry a `422`, an entirely blank entry is dropped silently, and each
field has a length ceiling.

| Section | Required | Max lengths |
|---|---|---|
| `work_experience[]` | `title`, `company` | `employment_type` 100; `awards` 20 items of 500 |
| `education[]` | `institution`, plus `degree` or `field` | `gpa` 100; `coursework`, `honors` 50 items of 200 |
| `certifications[]` | `name` | `expires` 100; `credential_url` 500; `description` 2000 |
| `projects[]` | `name` | each of `links.*` 500; dates 100; `highlights` 20 items of 500 |
| `publications[]` | `title` | `title` 500; `authors` 1000; `url` 500; `status` 100; `year` 100 |

A project whose **only** content is a link is not a blank row and is kept.

### `GET /profile/gaps` and publications

Publications are deliberately **not** gap-checked. Most people outside research
have none, so the nudge could only ever be dismissed, and a nudge that is always
noise trains users to dismiss the ones that are not.

### `profile_service.render_profile_text(parsed_json) -> str`

Not an endpoint -- a helper for other services. Renders the **whole** profile as
plain text, every section and every field above, nothing capped or summarised,
empty sections omitted entirely (an empty profile renders as `""`). It is what a
caller wants when a model must not miss a role because a summary truncated the
list. `utils/context_builder` keeps its own deliberately compact summary for the
chat system message, where the token budget is tight; the two are not
interchangeable.

---

## Supplementary import

A resume is one snapshot. The spreadsheet or long-form CV people keep alongside
it holds the detail the resume had no room for. `/profile/import` reads one of
those and proposes what the profile would look like with it folded in;
`/profile/import/apply` is what writes.

**Nothing about the file is stored.** It is parsed in memory and discarded, and
no proposal is cached server-side -- which is why the apply call takes the
reviewed proposal (and, optionally, the document text) back in its body.

### `POST /profile/import`

multipart `file`. Works with or without an existing profile: without one, the
merge runs against an empty profile and every entry comes back as `"added"`.

| Format | Read as |
|---|---|
| XLSX / XLSM | One markdown table per sheet, headed `## Sheet: <name>`. Cells stripped, newlines inside a cell joined with `" / "`, pipes escaped, whole numbers rendered without a decimal point |
| CSV | The same, as one table named after the file. The delimiter is sniffed, so a semicolon-separated export is still a table |
| DOCX / PDF | The resume parser's own readers |
| TXT / MD | Decoded as text |
| JSON | Pretty-printed; invalid JSON falls through as text rather than being refused |

The **extension** decides the format, with the content type as the fallback --
the opposite of `/profile/upload`. Browsers send `text/plain` for `.csv` and
`.md` alike, and trusting that first would flatten a spreadsheet into prose.

**References are never imported.** A sheet is skipped when its name contains
`LOR`/`LORs` (as a word -- "Colors" is safe), `reference`, `recommend`, or
`referee`, **or** when its header row pairs an email column with a phone column.
Those rows are other people's contact details. A skipped sheet is still reported,
with `skipped_reason`, so the user knows it was read and left out rather than
missed. A file whose only sheets are reference sheets is a `422`.

The merge itself is one Azure GPT-4o call (`temperature` 0.1, `max_tokens`
8000), preferring Azure because Groq's daily cap is spent on chat. A document
over ~60k characters is split **on sheet boundaries** and merged in sequential
passes, each pass taking the previous one's output as its "existing" profile --
sequential, not parallel, because pass two has to see what pass one added or a
role listed on two sheets is added twice.

Response `200`:

```json
{
  "proposal": { "...": "a full ParsedProfile" },
  "changes": [
    {
      "section": "work_experience",
      "kind": "added",
      "label": "Senior Backend Engineer at Kestrel Labs",
      "key": "kestrel labs|senior backend engineer",
      "index": 1,
      "fields": []
    },
    {
      "section": "education",
      "kind": "updated",
      "label": "Master of Technology, IIT Hyderabad",
      "key": "iit hyderabad|master of technology",
      "index": 0,
      "fields": ["gpa", "coursework"]
    },
    {
      "section": "skills",
      "kind": "unchanged",
      "label": "Python",
      "key": "python",
      "index": 0,
      "fields": []
    }
  ],
  "summary": {
    "added": 2,
    "updated": 1,
    "unchanged": 9,
    "removed": 0,
    "sections": {
      "work_experience": {"added": 1, "updated": 0, "unchanged": 1, "removed": 0},
      "education": {"added": 0, "updated": 1, "unchanged": 0, "removed": 0}
    }
  },
  "source": {
    "filename": "career.xlsx",
    "kind": "xlsx",
    "sheets": [
      {"name": "Education", "rows": 3, "cols": 7, "skipped_reason": null},
      {"name": "LORs", "rows": 12, "cols": 11,
       "skipped_reason": "References contain third-party contact details and are not imported."}
    ]
  },
  "document_text": "## Sheet: Education

| Degree | Institution | ...",
  "provider": "azure"
}
```

`document_text` is the extracted text **exactly as it was fed to the model**,
capped at 200,000 characters (the head is kept). The server stores nothing about
the upload between this call and the apply call, so this field is the only place
that text exists once the response has been sent -- send it straight back on
`/profile/import/apply` and it becomes the appended `raw_text`.

#### The diff is computed, not asked for

`changes` is produced **here**, by comparing the stored profile with the
proposal, and never by asking the model what it changed -- a model asked to
describe its own edits will confidently list one it did not make.

| Rule | |
|---|---|
| Identity | `work_experience`: company + title. `education`: institution + degree. `certifications`, `projects`: name. `publications`: title. `skills`, `achievements`: the string itself |
| Normalisation | Case-folded, punctuation and repeated spacing removed, so "Kestrel Labs, Inc." matches "kestrel labs inc" |
| `added` | No existing entry has that key |
| `updated` | Matched, and at least one field differs. `fields` names them |
| `unchanged` | Matched, every field equal |
| `removed` | An existing entry the proposal does not contain. The merge prompt forbids dropping anything, so this should always be empty -- it is computed because a review screen that silently omits a role the model lost is worse than one that shows it |
| Empty vs absent | `null` and `""` are the same absence, so filling a field with `""` is not an update |
| Order | Section order, then the proposal's own order. `index` is the position in the **proposal's** section list, and `null` for `removed` |
| `summary` (the section) | Diffed too, as a single entry labelled "Professional summary" |

`key` is stable across re-imports, so a client can keep a per-entry decision
through a refresh.

| Status | Cause |
|---|---|
| 400 | Not an importable format, or the file is corrupt |
| 413 | Over 10MB |
| 422 | Empty file, or nothing importable in it (including "every sheet was references") |
| 502 | The merge model was unreachable or returned no JSON |

### `POST /profile/import/apply`

```json
{
  "parsed_json": { "...": "the proposal, optionally hand-edited" },
  "sections": ["skills", "publications"],
  "filename": "career.xlsx",
  "document_text": "## Sheet: Skills\n| Kafka |"
}
```

| Field | Notes |
|---|---|
| `parsed_json` | The whole proposal. Only the named sections are read from it |
| `sections` | Which sections to write. Each replaces that section wholesale; anything not named is untouched. An unknown name is a `422`, not a silent no-op. An empty list is a valid, empty, save |
| `filename` | For the `raw_text` header |
| `document_text` | The `document_text` from the import response, echoed back verbatim. Optional -- omit it and `raw_text` is left alone |

The submitted sections go through the **same strict validation as `PATCH
/profile`**, including its `errors` list: an import is still the user's decision
to write something, and a row that vanished on save with a `200` would be data
loss whether a model or a keyboard produced it. A `422` writes nothing at all.
Entirely blank entries are dropped without an error, as everywhere else.

When `document_text` is present it is appended to `raw_text` under a dated
header:

```text
<existing raw_text>

--- Imported from career.xlsx on 2026-09-05 ---
## Sheet: Education
...
```

`raw_text` is capped at 200,000 characters, keeping the **tail** -- the newest
import is the one the user just reviewed.

`200` returns the full `ProfileResponse`. A user with no profile row yet gets one
created, so an import can be the first thing they ever do.

---

## Private instances

`ALLOWED_USER_EMAILS` (comma-separated, empty by default) turns a shared
Supabase project into a personal deployment without touching the project's
sign-up settings. Empty means open, which is the behaviour that existed before
the setting.

When it is set, every protected route additionally requires the verified token's
`email` claim -- or `user_metadata.email`, which is where some providers put it
-- to appear on the list, compared case-insensitively. A token with no email
claim is not on the list.

A rejected caller gets:

```json
{ "detail": "This Applify instance is private." }
```

**403, not 401.** The token is genuine and re-authenticating cannot help, so a
401 would only send the frontend round a login loop. The message names nothing
about who *is* allowed. Signature verification still runs first: an invalid
token is a 401 on a private instance exactly as on an open one.

---

## Account

### `DELETE /account`

Deletes the caller's data and their Supabase login. Irreversible, with no
confirmation step in the API -- the confirmation belongs in the UI, which is
where the user can be told what they are about to lose.

`204`, no body.

What goes, in one transaction: the profile, every job chat (soft-deleted ones
included), and -- through the `ON DELETE CASCADE` on their `chat_id` -- every
message, analysis, generated output, and tracker row. Tracker rows are also
swept by `user_id` first, which catches one whose chat an earlier partial run
already removed.

Then the Supabase Auth user, through the Admin API with
`SUPABASE_SERVICE_ROLE_KEY` (10s timeout), so the address can sign up again from
scratch. A `404` from Supabase counts as success -- the login is already gone,
which is the state that was asked for, and a retry of a partly finished deletion
has to be able to finish.

**The order is deliberate: database first, auth second.** Deleting the login
first and then failing on the database would leave rows nobody can reach, sign in
as, or delete -- the user has no token any more. Failing the other way round
leaves a login with no data behind it, which is recoverable and is reported
rather than hidden.

| Status | Cause |
|---|---|
| 204 | Both are gone |
| 401 | No usable token |
| 501 | `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_URL`) is unset. **Nothing is deleted** -- a half-deleted account is worse than a refused one, and the fix is a deployment setting, not a retry |
| 502 | The rows were removed but Supabase Auth would not delete the login. The message says exactly that and points at the `X-Request-ID`, which is on the log line too |

The service role key bypasses row level security. It is never logged, never
returned, and a failure message quotes only the status code Supabase gave --
never its body, which can echo the request that carried the key.
