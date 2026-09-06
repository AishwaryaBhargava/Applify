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
  /** "Full-time", "Internship", ... Free-form; the editor offers a short list. */
  employment_type: string | null
  /** Recognition earned in this role, one per entry. */
  awards: string[]
}

/** Mirrors `Education` in backend/app/api/schemas/profile.py. */
export interface Education {
  degree: string | null
  institution: string | null
  field: string | null
  start_date: string | null
  end_date: string | null
  details: string | null
  /** Free-form ("8.4/10", "3.9 GPA"): grading scales differ by country. */
  gpa: string | null
  coursework: string[]
  honors: string[]
}

/** Mirrors `Certification` in backend/app/api/schemas/profile.py. */
export interface Certification {
  name: string | null
  issuer: string | null
  year: string | null
  expires: string | null
  credential_url: string | null
  description: string | null
}

/**
 * The three places a project usually lives. Kept as named fields rather than a
 * list so the view can label each one ("Code", "Live", "Demo") instead of
 * showing three anonymous URLs.
 */
export interface ProjectLinks {
  github: string | null
  live: string | null
  demo: string | null
}

/** Mirrors `Project` in backend/app/api/schemas/profile.py. */
export interface Project {
  name: string | null
  description: string | null
  technologies: string[]
  /**
   * The original single link, kept for profiles parsed before `links` existed.
   * The view falls back to it only when none of the three named links is set.
   */
  link: string | null
  start_date: string | null
  end_date: string | null
  highlights: string[]
  links: ProjectLinks
}

/**
 * A paper, article, or talk. Mirrors `Publication` in
 * backend/app/api/schemas/profile.py — `title` is the one required field, so it
 * is a plain string here (empty while a new row is being typed) rather than
 * nullable like the rest.
 */
export interface Publication {
  title: string
  authors: string | null
  url: string | null
  /** "Published", "Under review", "Preprint" — free-form. */
  status: string | null
  year: string | null
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
  publications: Publication[]
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
/* Supplementary file import (POST /profile/import)                    */
/* ------------------------------------------------------------------ */

/**
 * What the import would do to one entry.
 *
 * `added` — no entry in the current profile matches it. `updated` — a matching
 * entry gains or changes fields (`fields` names which). `unchanged` — the file
 * says exactly what the profile already says, kept in the response so the
 * review screen can account for every row rather than quietly dropping it.
 * `removed` — the proposal drops an entry the profile has.
 */
export type ImportChangeKind = 'added' | 'updated' | 'unchanged' | 'removed'

/** One proposed entry-level change, as the review screen lists it. */
export interface ImportChange {
  /** A `ProfileSectionKey` in practice; typed wide so an unknown section from
   *  a newer backend still renders rather than being silently dropped. */
  section: string
  kind: ImportChangeKind
  /** Human-readable identity of the entry ("Senior Engineer at Acme"). */
  label: string
  /** The normalised identity the diff matched on — stable across a re-import. */
  key: string
  /** Position in the *proposal's* section list; null for a removed entry. */
  index: number | null
  /** The field names that differ. Only meaningful for `updated`. */
  fields: string[]
}

/** How many entries fall into each change kind. */
export interface ImportChangeCounts {
  added: number
  updated: number
  unchanged: number
  removed: number
}

/**
 * Totals across the whole proposal, plus the same counts per section.
 *
 * The totals are the server's own, not a sum the review screen computes: a
 * change kind this build does not render yet still has to be counted honestly.
 */
export interface ImportSummary extends ImportChangeCounts {
  sections: Record<string, ImportChangeCounts>
}

/**
 * One sheet (or one logical block) the parser looked at. `skipped_reason` is
 * set when it read the sheet and decided against using it — an empty tab, a
 * layout it could not map — and the review screen shows it as an amber note so
 * a user who expected that data knows why it is missing.
 */
export interface ImportSheet {
  name: string
  rows: number
  cols: number
  skipped_reason?: string | null
}

/** Where the proposal came from: the uploaded file and what was read from it. */
export interface ImportSource {
  /** Null when the upload carried no filename at all. */
  filename: string | null
  /** The parser's own label for the format: xlsx, csv, docx, pdf, txt, md, json. */
  kind: string
  sheets: ImportSheet[]
}

/**
 * Body of `POST /profile/import` — a merge preview, saved nowhere.
 *
 * `proposal` is the *whole* profile as it would be after the merge, not a
 * delta, which is exactly what `POST /profile/import/apply` takes back: the
 * user picks sections, and each picked section is written wholesale.
 */
export interface ImportProposal {
  proposal: ParsedProfile
  changes: ImportChange[]
  summary: ImportSummary
  source: ImportSource
  /** The extraction model that read the file. Shown as provenance. */
  provider?: string | null
  /**
   * The text extracted from the uploaded file.
   *
   * Never rendered — it is carried purely so `/profile/import/apply` can be
   * given it back. The server stores no upload and caches no proposal, so this
   * round trip is the only way the applied profile's `raw_text` can keep the
   * source the import came from.
   */
  document_text?: string | null
}

/**
 * Body of `POST /profile/import/apply`.
 *
 * The server keeps nothing between the two calls — no upload stored, no
 * proposal cached — so the reviewed proposal travels back in full, and
 * `filename` is echoed with it for the raw-text header the backend writes.
 */
export interface ImportApplyRequest {
  parsed_json: ParsedProfile
  sections: ProfileSectionKey[]
  filename?: string | null
  /** The extracted document text, when the client still holds it. */
  document_text?: string | null
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
  /**
   * The stored ATS keyword match, when one has been run for this chat.
   * Optional as well as nullable: a backend from before the keyword phase
   * omits the key entirely, and the panel's "not run yet" state is the same
   * either way.
   */
  keyword_match?: KeywordMatch | null
}

/* ------------------------------------------------------------------ */
/* ATS keyword match (POST /chats/{id}/keywords)                       */
/* ------------------------------------------------------------------ */

/**
 * What kind of thing a keyword is. The panel groups by importance rather than
 * category, but `skill` and `tool` are the two that can be added straight to
 * the profile's skills list, which is why the distinction is carried.
 */
export type KeywordCategory =
  | 'skill'
  | 'tool'
  | 'qualification'
  | 'responsibility'
  | 'soft_skill'
  | 'domain'

/** How badly the posting wants it. Required misses are the ones that matter. */
export type KeywordImportance = 'required' | 'preferred'

/**
 * One keyword extracted from the job description, matched against the profile
 * and — once a resume has been generated here — against that resume too.
 *
 * `in_resume` is `null` when there is no tailored resume to check against,
 * which is a different statement from `false` ("there is one, and the keyword
 * is not in it"). `evidence` is the profile snippet the match was found in.
 */
export interface KeywordMatchItem {
  keyword: string
  category: KeywordCategory
  importance: KeywordImportance
  /**
   * The other spellings that counted as this keyword — the model's, plus the
   * backend's built-in equivalences. This is what answers "why did *postgres*
   * satisfy *PostgreSQL*", so it is shown beside the evidence rather than
   * dropped. Defaulted server-side, so an older payload without it is fine.
   */
  aliases?: string[]
  in_profile: boolean
  in_resume: boolean | null
  evidence: string | null
}

/** Body of POST /chats/{id}/keywords, and `keyword_match` on GET /chats/{id}. */
export interface KeywordMatch {
  /** 0-100. Weighted toward the required keywords, like an ATS would be. */
  match_percent: number
  required_matched: number
  required_total: number
  preferred_matched: number
  preferred_total: number
  keywords: KeywordMatchItem[]
  /** The required keywords absent from the profile, for the missing column. */
  missing_required: string[]
  generated_at: string
  /** Which model produced the extraction — "groq" or "azure". */
  provider: string
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
 * How much the user cares about this one. Nullable rather than defaulted to
 * "medium": an unset priority is not an opinion, and drawing every untouched
 * row with an amber dot would make the dot meaningless.
 */
export type TrackerPriority = 'low' | 'medium' | 'high'

/** The sort keys `GET /tracker?sort=` accepts. Every one is descending. */
export type TrackerSort =
  | 'created_at'
  | 'applied_at'
  | 'next_action_date'
  | 'fit_score'

/**
 * Where the posting came from. A free string on the wire — the select is a
 * convenience, not a constraint, and a value from an older row still renders.
 */
export const TRACKER_SOURCES = [
  'LinkedIn',
  'Company site',
  'Referral',
  'Recruiter',
  'Job board',
  'Other',
] as const

export type TrackerSource = (typeof TRACKER_SOURCES)[number]

/**
 * The subset of a tracker row the user may edit, and exactly the body
 * `PATCH /tracker/{chat_id}` accepts. Every field is optional: the drawer
 * sends only what changed.
 *
 * Setting `status` to `applied` fills `applied_at` in server-side, so the
 * response is adopted wholesale rather than merged field by field.
 */
export interface TrackerEntryPatch {
  status?: TrackerStatus
  job_url?: string | null
  location?: string | null
  salary?: string | null
  source?: string | null
  /** ISO timestamp. */
  applied_at?: string | null
  next_action?: string | null
  /** `YYYY-MM-DD`, the value a native date input produces. */
  next_action_date?: string | null
  notes?: string | null
  priority?: TrackerPriority | null
}

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

  /* --- The pipeline fields the drawer edits. All optional, because the row
     the sidebar writes optimistically has none of them yet. --- */

  /** The posting itself, captured when the chat was created or added later. */
  job_url?: string | null
  location?: string | null
  /** Free text — "£70-85k", "competitive". Never parsed. */
  salary?: string | null
  source?: string | null
  /** ISO timestamp. Filled server-side the first time status becomes applied. */
  applied_at?: string | null
  /** "Follow up with the recruiter", "Prep the system design round". */
  next_action?: string | null
  /** `YYYY-MM-DD`. */
  next_action_date?: string | null
  notes?: string | null
  priority?: TrackerPriority | null

  /* --- Server-computed, read-only. --- */

  /** Whole days between `applied_at` and now; null when never applied. */
  days_since_applied?: number | null
  /** True when `next_action_date` is today or already past. */
  next_action_due?: boolean
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
