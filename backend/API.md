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
| 404 | Not yours, deleted, or never existed |
| 409 | The user has no profile yet (`Upload your resume first`) |
| 422 | Request body failed validation, or the chat has no JD |
| 502 | The model provider was unreachable or returned nothing usable |

---

## Health

### `GET /health`

Unauthenticated. `200 {"status": "ok"}`.

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
| `PATCH` | `/profile` | Section-wise manual enrichment |
| `GET` | `/profile/gaps` | Rule-based nudges for missing or thin sections |

`ProfileResponse`: `{user_id, raw_text, parsed_json, created_at, updated_at}`.

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
depth-specific detail:

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
  "verdict": "Apply, but lead with the payments work."
}
```

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

data: {"type":"done","message_id":"7c9e...","content":"Your Python experience fits."}

```

| Event | Fields | Meaning |
|---|---|---|
| `start` | `message_id`, `kind` | The assistant message's id, chosen up front, and the detected intent. Render an empty bubble and stream into it. |
| `token` | `content` | One chunk. Append it; chunks are not line- or word-aligned. |
| `done` | `message_id`, `content`, (`output_id`, `resume_type`) | The full text. The message is persisted at this point. For an output `kind` the event also carries `output_id`, and for `resume` the tracker's new `resume_type`. The stream closes. |
| `error` | `message`, `message_id`, `partial`, `content` | Generation failed. `partial: true` means `content` did stream and **has been persisted** under `message_id` -- leave it on screen and offer a retry. `partial: false` means nothing was stored. |

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

Chat replies come from Groq (`GROQ_MODEL`, streaming, `max_tokens` 2048). The
context is assembled by `utils/context_builder.build_messages`:

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

data: {"type":"done","message_id":"7c9e...","content":"# Priya Raman\n...","output_id":"1a2b...","resume_type":"tailored"}

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
