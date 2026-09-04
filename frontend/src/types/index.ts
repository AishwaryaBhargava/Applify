/**
 * Shared TypeScript interfaces for Applify.
 * These mirror the backend SQLAlchemy models and API schemas.
 */

/* ------------------------------------------------------------------ */
/* Profile                                                             */
/* ------------------------------------------------------------------ */

export interface WorkExperience {
  id?: string
  title: string
  company: string
  location?: string
  start_date?: string
  end_date?: string
  is_current?: boolean
  description?: string
  highlights?: string[]
}

export interface Education {
  id?: string
  degree: string
  institution: string
  field_of_study?: string
  start_date?: string
  end_date?: string
  grade?: string
}

export interface ParsedProfile {
  full_name?: string
  email?: string
  phone?: string
  location?: string
  headline?: string
  summary?: string
  work_experience: WorkExperience[]
  education: Education[]
  skills: string[]
  certifications: string[]
  projects: string[]
  achievements: string[]
}

export interface Profile {
  id: string
  user_id: string
  raw_text: string | null
  parsed_json: ParsedProfile
  created_at: string
  updated_at: string
}

export interface ProfileGap {
  id: string
  section: keyof ParsedProfile | string
  message: string
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
