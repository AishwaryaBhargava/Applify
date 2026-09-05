/**
 * Shared TypeScript interfaces for Applify.
 * These mirror the backend SQLAlchemy models and API schemas.
 */

/* ------------------------------------------------------------------ */
/* Profile                                                             */
/* ------------------------------------------------------------------ */

/**
 * A single role in the user's work history.
 * Mirrors `WorkExperience` in backend/app/api/schemas/profile.py. Every field
 * is nullable there, so every field is nullable here.
 */
export interface WorkExperience {
  title: string | null
  company: string | null
  location: string | null
  /** Free-form, as written on the resume ("Jan 2022"). Never normalized. */
  start_date: string | null
  end_date: string | null
  current: boolean
  highlights: string[]
}

/** Mirrors `Education` in backend/app/api/schemas/profile.py. */
export interface Education {
  degree: string | null
  institution: string | null
  field: string | null
  start_date: string | null
  end_date: string | null
  details: string | null
}

/** Mirrors `Certification` in backend/app/api/schemas/profile.py. */
export interface Certification {
  name: string | null
  issuer: string | null
  year: string | null
}

/** Mirrors `Project` in backend/app/api/schemas/profile.py. */
export interface Project {
  name: string | null
  description: string | null
  technologies: string[]
  link: string | null
}

/**
 * The structured resume parse — the single contract shared with
 * `ParsedProfile` in backend/app/api/schemas/profile.py, in the order the
 * profile page renders them.
 *
 * The backend sends `summary` as `null` when absent; `normalizeProfile` in
 * services/profile.ts coerces it to `''` so components never null-check.
 */
export interface ParsedProfile {
  summary: string
  work_experience: WorkExperience[]
  education: Education[]
  skills: string[]
  certifications: Certification[]
  projects: Project[]
  achievements: string[]
}

/** The section names PATCH /profile accepts, and gap detection reports on. */
export type ProfileSectionKey = keyof ParsedProfile

/** Shape returned by GET /profile, POST /profile/upload and PATCH /profile. */
export interface Profile {
  user_id: string
  raw_text?: string | null
  parsed_json: ParsedProfile
  created_at: string
  updated_at: string
}

/** `missing` — the section is empty. `thin` — present but underweight. */
export type ProfileGapSeverity = 'missing' | 'thin'

/**
 * A nudge for a missing or thin section. `id` is stable across requests so a
 * dismissal can be persisted in localStorage and stay dismissed.
 */
export interface ProfileGap {
  id: string
  /** A `ProfileSectionKey` in practice; typed wide so an unknown section from
   *  a newer backend still renders rather than being silently dropped. */
  section: string
  severity: ProfileGapSeverity
  message: string
}

/** Body of GET /profile/gaps. */
export interface ProfileGapsResponse {
  gaps: ProfileGap[]
}

/**
 * One field-level complaint from `PATCH /profile`'s 422.
 *
 * `index` is the position in the **submitted** list, so it lines up with the
 * editor's rows, and is `null` for a section-level failure such as an
 * over-long summary. Mirrors the entries in the response's `errors` array, and
 * is the shape `lib/profileValidation` produces client-side so both sources of
 * truth render identically.
 */
export interface ProfileFieldError {
  section: string
  index: number | null
  field: string
  message: string
}

/**
 * Body of a `PATCH /profile` 422. `detail` is the toast sentence; `errors` is
 * what the profile page highlights on. A malformed body (a string where a list
 * belongs) is pydantic's own 422 and carries no `errors` key.
 */
export interface ProfileUpdateErrorResponse {
  detail?: string
  errors?: ProfileFieldError[]
}

/* ------------------------------------------------------------------ */
/* Job chats and messages                                              */
/* ------------------------------------------------------------------ */

/** The two analysis depths. Mirrors `AnalysisType` in schemas/analysis.py. */
export type AnalysisType = 'quick' | 'detailed'

/**
 * A job chat as the sidebar and the chat page see it.
 * Mirrors `ChatResponse` in backend/app/api/schemas/chats.py.
 *
 * `company` and `jd_text` are nullable: the backend accepts a chat created
 * from a title alone. `has_analysis` and `resume_type` are computed by the
 * route (from the analysis table and the chat's tracker entry) so the sidebar
 * never has to fan out to /tracker just to draw a row.
 */
export interface JobChat {
  id: string
  title: string
  company: string | null
  jd_text: string | null
  /** null until an analysis has been run, then the depth that ran. */
  analysis_type: AnalysisType | null
  created_at: string
  has_analysis: boolean
  resume_type: ResumeType
}

export type ChatRole = 'user' | 'assistant' | 'system'

/**
 * What produced a message. `chat` is an ordinary turn, `analysis` is the
 * rendered fit analysis, and the rest are generated documents (Phase 7).
 * Mirrors `MESSAGE_KINDS` in backend/app/api/schemas/messages.py.
 */
export type MessageKind = 'chat' | 'analysis' | 'resume' | 'cover_letter' | 'answer'

/** Mirrors `MessageResponse` in backend/app/api/schemas/messages.py. */
export interface ChatMessage {
  id: string
  chat_id: string
  role: ChatRole
  content: string
  kind: MessageKind
  created_at: string
}

/**
 * A message as the thread renders it. The two extra flags are client-only and
 * never come from the server: `pending` marks the assistant bubble that is
 * still streaming, `errored` marks one whose stream failed or was stopped so
 * the bubble can offer a retry alongside whatever text did arrive.
 */
export interface ThreadMessage extends ChatMessage {
  pending?: boolean
  errored?: boolean
  errorMessage?: string
}

/** Body of GET /chats/{id} — everything needed to rebuild the page. */
export interface ChatDetail extends JobChat {
  messages: ChatMessage[]
  analysis: Analysis | null
}

/* ------------------------------------------------------------------ */
/* Streaming (POST /chats/{id}/messages, text/event-stream)            */
/* ------------------------------------------------------------------ */

/** First frame: names the message id the tokens belong to and its kind. */
export interface StreamStartEvent {
  type: 'start'
  message_id: string
  kind: MessageKind
}

/** One chunk of assistant text. */
export interface StreamTokenEvent {
  type: 'token'
  content: string
}

/**
 * Final frame on success: the full text as it was persisted.
 *
 * A document turn — one whose `start` named a `kind` other than `chat`, whether
 * it came from the intent router or from `POST /chats/{id}/outputs` — carries
 * two extra fields: the id of the `generated_outputs` row it was filed under,
 * and, for a resume, the tracker's new `resume_type`. Both are what let the
 * tracker and the outputs list update without a refetch.
 */
export interface StreamDoneEvent {
  type: 'done'
  message_id: string
  content: string
  output_id?: string
  resume_type?: ResumeType
}

/**
 * Final frame on failure. The backend persists whatever streamed before the
 * failure and reports it back in `content`, so the thread can show the partial
 * answer rather than dropping it.
 */
export interface StreamErrorEvent {
  type: 'error'
  message: string
  message_id?: string
  partial?: boolean
  content?: string
}

export type StreamEvent =
  | StreamStartEvent
  | StreamTokenEvent
  | StreamDoneEvent
  | StreamErrorEvent

/* ------------------------------------------------------------------ */
/* Analysis                                                            */
/* ------------------------------------------------------------------ */

/**
 * One skill compared between the JD and the profile, from a detailed
 * breakdown. Mirrors `SkillAssessment` in schemas/analysis.py.
 */
export interface DetailedSkill {
  skill: string
  required_by_jd: boolean
  user_has: boolean
  /** What in the profile backs this up. Empty when the user does not have it. */
  evidence: string
  /** Why the gap matters, when there is one. */
  gap_reasoning: string
  /** What the user could do about it. */
  suggestion: string
}

/**
 * The depth-specific payload. A quick snapshot carries only the four summary
 * fields; a detailed breakdown adds `skills` and `narrative`. Every field is
 * optional so a payload from a newer backend still renders rather than
 * throwing, and the index signature keeps unknown keys addressable.
 */
export interface AnalysisFullJson {
  fit_score?: number
  strengths?: string[]
  gaps?: string[]
  verdict?: string
  skills?: DetailedSkill[]
  narrative?: string
  [key: string]: unknown
}

/**
 * A stored analysis. `fit_score`, `strengths`, `gaps` and `verdict` are the
 * summary — the same four fields whichever depth ran, so the card renders
 * identically. Mirrors `AnalysisResponse` in schemas/analysis.py.
 */
export interface Analysis {
  id: string
  chat_id: string
  type: AnalysisType
  fit_score: number
  strengths: string[]
  gaps: string[]
  verdict: string
  full_json: AnalysisFullJson
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Tracker                                                             */
/* ------------------------------------------------------------------ */

export type TrackerStatus =
  | 'not_applied'
  | 'applied'
  | 'interviewing'
  | 'offer'
  | 'rejected'

/** Mirrors `ResumeType` in backend/app/api/schemas/tracker.py. */
export type ResumeType = 'unaltered' | 'tailored'

/**
 * A tracker row, flattened for the Phase 8 table: everything a row renders
 * comes from this one object. Mirrors `TrackerEntry` in
 * backend/app/api/schemas/tracker.py.
 *
 * `job_title` and `date_added` are the server's names; `title` and
 * `created_at` are the Phase 6 names the sidebar's optimistic row still uses,
 * and the backend sends both. Read them through `entryTitle` / `entryDate` in
 * lib/format.ts rather than picking one here.
 */
export interface TrackerEntry {
  id: string
  chat_id: string
  /** Absent on the optimistic entry the sidebar creates alongside a chat. */
  user_id?: string
  /** The chat's title. Absent only on a locally-created optimistic row. */
  job_title?: string | null
  /** The Phase 6 alias for `job_title`; the backend sends both. */
  title?: string | null
  company: string | null
  /** When the chat was started. Falls back to `created_at` when absent. */
  date_added?: string | null
  /** null until an analysis has been run, then the depth that ran. */
  analysis_type?: AnalysisType | null
  status: TrackerStatus
  resume_type: ResumeType
  /** From the chat's analysis, when it has one. */
  fit_score?: number | null
  created_at: string
  updated_at: string
}

/* ------------------------------------------------------------------ */
/* Generated outputs                                                   */
/* ------------------------------------------------------------------ */

export type OutputType = 'resume' | 'cover_letter' | 'answer'

export interface GeneratedOutput {
  id: string
  chat_id: string
  output_type: OutputType
  content: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Misc                                                                */
/* ------------------------------------------------------------------ */

export interface ApiError {
  detail: string
  status?: number
}

export interface HealthResponse {
  status: string
}
