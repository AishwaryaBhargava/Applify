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

/* ------------------------------------------------------------------ */
/* Job chats and messages                                              */
/* ------------------------------------------------------------------ */

export type AnalysisType = 'quick' | 'detailed'

export interface JobChat {
  id: string
  user_id: string
  title: string
  company: string
  jd_text: string
  analysis_type: AnalysisType | null
  created_at: string
}

export type ChatRole = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: string
  chat_id: string
  role: ChatRole
  content: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Analysis                                                            */
/* ------------------------------------------------------------------ */

export interface QuickSnapshot {
  fit_score: number
  strengths: string[]
  gaps: string[]
  verdict: string
}

export interface SkillComparison {
  skill: string
  required: boolean
  matched: boolean
  reasoning: string
  suggestion?: string
}

export interface DetailedBreakdown {
  fit_score: number
  narrative: string
  skill_comparison: SkillComparison[]
  strengths: string[]
  gaps: string[]
  verdict: string
}

export interface Analysis {
  id: string
  chat_id: string
  type: AnalysisType
  fit_score: number
  strengths: string[]
  gaps: string[]
  verdict: string
  full_json: QuickSnapshot | DetailedBreakdown | null
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

export type ResumeType = 'unaltered' | 'ai_tailored'

export interface TrackerEntry {
  id: string
  chat_id: string
  user_id: string
  title: string
  company: string
  analysis_type: AnalysisType | null
  status: TrackerStatus
  resume_type: ResumeType
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
