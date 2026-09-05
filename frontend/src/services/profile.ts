import type { AxiosProgressEvent } from 'axios'
import api, { apiErrorMessage, apiErrorStatus } from './api'
import type {
  Certification,
  Education,
  ParsedProfile,
  Profile,
  ProfileGap,
  ProfileGapsResponse,
  Project,
  WorkExperience,
} from '../types'

/** Empty parse, used to normalize a profile the backend returns half-filled. */
export function emptyParsedProfile(): ParsedProfile {
  return {
    summary: '',
    work_experience: [],
    education: [],
    skills: [],
    certifications: [],
    projects: [],
    achievements: [],
  }
}

/** A blank role, used by the "Add entry" button on the profile page. */
export function emptyWorkExperience(): WorkExperience {
  return {
    title: '',
    company: '',
    location: '',
    start_date: '',
    end_date: '',
    current: false,
    highlights: [],
  }
}

/** A blank education entry. */
export function emptyEducation(): Education {
  return {
    degree: '',
    institution: '',
    field: '',
    start_date: '',
    end_date: '',
    details: '',
  }
}

/** A blank certification. */
export function emptyCertification(): Certification {
  return { name: '', issuer: '', year: '' }
}

/** A blank project. */
export function emptyProject(): Project {
  return { name: '', description: '', technologies: [], link: '' }
}

/** Coerces anything the backend might send for a string list into a string list. */
function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

/** Coerces an object list, dropping anything that is not an object. */
function asObjectList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value.filter((v) => v && typeof v === 'object') as T[]) : []
}

/**
 * Guarantees every section exists in the shape components expect: arrays are
 * arrays and `summary` is a string, whatever the backend sends back. The
 * backend sends `summary: null` for a resume with no summary, so a plain
 * object spread is not enough — every section is coalesced explicitly.
 */
export function normalizeProfile(profile: Profile): Profile {
  const parsed = (profile.parsed_json ?? {}) as Partial<ParsedProfile>
  return {
    ...profile,
    parsed_json: {
      summary: typeof parsed.summary === 'string' ? parsed.summary : '',
      work_experience: asObjectList<WorkExperience>(parsed.work_experience),
      education: asObjectList<Education>(parsed.education),
      skills: asStringList(parsed.skills),
      certifications: asObjectList<Certification>(parsed.certifications),
      projects: asObjectList<Project>(parsed.projects),
      achievements: asStringList(parsed.achievements),
    },
  }
}

/**
 * Result of GET /profile. A missing profile (404) is a normal outcome for a
 * new user, so it is returned as a typed result rather than thrown.
 */
export type ProfileResult =
  | { status: 'ok'; profile: Profile }
  | { status: 'missing' }
  | { status: 'error'; message: string; statusCode?: number }

/** GET /profile — current user's full profile. 404 means "not uploaded yet". */
export async function getProfile(): Promise<ProfileResult> {
  try {
    const { data } = await api.get<Profile>('/profile')
    return { status: 'ok', profile: normalizeProfile(data) }
  } catch (error) {
    const statusCode = apiErrorStatus(error)
    if (statusCode === 404) return { status: 'missing' }
    return { status: 'error', message: apiErrorMessage(error), statusCode }
  }
}

/**
 * A resume upload is a file transfer followed by an LLM parse on the server,
 * so it needs far longer than an ordinary call. Four times the default.
 */
export const UPLOAD_TIMEOUT_MS = 120_000

/**
 * POST /profile/upload — multipart resume upload (PDF or DOCX).
 *
 * Throws on failure so the caller can show the message and offer a retry.
 * Deliberately excluded from the automatic retry in services/api: a repeat
 * would bill a second parse of a file the first attempt may well have stored.
 */
export async function uploadResume(
  file: File,
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<Profile> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<Profile>('/profile/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: UPLOAD_TIMEOUT_MS,
    onUploadProgress,
  })
  return normalizeProfile(data)
}

/**
 * PATCH /profile — replaces the sections present in `patch` and leaves the
 * rest untouched.
 *
 * Sections are sent at the top level (`{"skills": [...]}`), which is the shape
 * `ProfileUpdateRequest` reads first. A section that is present replaces that
 * section wholesale, so callers must send the whole array, never a delta.
 */
export async function updateProfile(
  patch: Partial<ParsedProfile>,
): Promise<Profile> {
  const { data } = await api.patch<Profile>('/profile', patch)
  return normalizeProfile(data)
}

/**
 * GET /profile/gaps — missing or thin sections of the current profile.
 * The response is `{"gaps": [...]}`; the wrapper is unwrapped here so callers
 * only ever see the list.
 */
export async function getProfileGaps(): Promise<ProfileGap[]> {
  const { data } = await api.get<ProfileGapsResponse>('/profile/gaps')
  return Array.isArray(data?.gaps) ? data.gaps : []
}
