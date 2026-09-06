import type { AxiosProgressEvent } from 'axios'
import api, { apiErrorBody, apiErrorMessage, apiErrorStatus } from './api'
import type {
  Certification,
  Education,
  ImportApplyRequest,
  ImportProposal,
  ParsedProfile,
  Profile,
  ProfileFieldError,
  ProfileGap,
  ProfileGapsResponse,
  ProfileSectionKey,
  ProfileUpdateErrorResponse,
  Project,
  ProjectLinks,
  Publication,
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
    publications: [],
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
    employment_type: '',
    awards: [],
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
    gpa: '',
    coursework: [],
    honors: [],
  }
}

/** A blank certification. */
export function emptyCertification(): Certification {
  return {
    name: '',
    issuer: '',
    year: '',
    expires: '',
    credential_url: '',
    description: '',
  }
}

/** Blank project links — always an object, never null, so `.github` is safe. */
export function emptyProjectLinks(): ProjectLinks {
  return { github: '', live: '', demo: '' }
}

/** A blank project. */
export function emptyProject(): Project {
  return {
    name: '',
    description: '',
    technologies: [],
    link: '',
    start_date: '',
    end_date: '',
    highlights: [],
    links: emptyProjectLinks(),
  }
}

/** A blank publication. */
export function emptyPublication(): Publication {
  return { title: '', authors: '', url: '', status: '', year: '' }
}

/** Coerces anything the backend might send for a string list into a string list. */
function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

/** Coerces an object list, dropping anything that is not an object. */
function asObjectList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value.filter((v) => v && typeof v === 'object') as T[]) : []
}

/** Reads one nullable string field off a raw entry. */
function asText(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Fills in every field of one entry, so a profile stored before a field existed
 * renders (and edits) exactly like one stored after.
 *
 * The blank entry is the template: whatever the backend actually sent wins,
 * field by field, and anything it did not send takes the blank's value. Without
 * this, a role saved last month has `awards: undefined` and the awards box
 * renders as `undefined` the first time someone opens the editor.
 */
function withDefaults<T extends object>(blank: T, raw: unknown): T {
  const source = (raw ?? {}) as Record<string, unknown>
  const out = { ...blank } as Record<string, unknown>
  for (const key of Object.keys(blank)) {
    const value = source[key]
    if (value === undefined || value === null) continue
    const fallback = (blank as Record<string, unknown>)[key]
    if (Array.isArray(fallback)) out[key] = asStringList(value)
    else if (typeof fallback === 'boolean') out[key] = value === true
    else out[key] = value
  }
  return out as T
}

function normalizeWorkExperience(raw: unknown): WorkExperience {
  return withDefaults(emptyWorkExperience(), raw)
}

function normalizeEducation(raw: unknown): Education {
  return withDefaults(emptyEducation(), raw)
}

function normalizeCertification(raw: unknown): Certification {
  return withDefaults(emptyCertification(), raw)
}

function normalizeProject(raw: unknown): Project {
  const project = withDefaults(emptyProject(), raw)
  const links = (raw as { links?: unknown } | null)?.links
  const source = (links ?? {}) as Record<string, unknown>
  project.links = {
    github: asText(source.github),
    live: asText(source.live),
    demo: asText(source.demo),
  } satisfies ProjectLinks
  return project
}

function normalizePublication(raw: unknown): Publication {
  const publication = withDefaults(emptyPublication(), raw)
  // `title` is the only non-nullable field in the contract; a proposal that
  // somehow omits it still has to render rather than crash the review screen.
  publication.title = typeof publication.title === 'string' ? publication.title : ''
  return publication
}

/**
 * Guarantees every section exists in the shape components expect: arrays are
 * arrays, `summary` is a string, and every field of every entry is present,
 * whatever the backend sends back. The backend sends `summary: null` for a
 * resume with no summary, so a plain object spread is not enough — every
 * section is coalesced explicitly.
 */
export function normalizeProfile(profile: Profile): Profile {
  return { ...profile, parsed_json: normalizeParsedProfile(profile.parsed_json) }
}

/**
 * The section-by-section half of `normalizeProfile`, exported because the
 * import proposal is a bare `ParsedProfile` rather than a whole profile row and
 * needs exactly the same treatment before the review screen reads it.
 */
export function normalizeParsedProfile(raw: unknown): ParsedProfile {
  const parsed = (raw ?? {}) as Partial<ParsedProfile>
  return {
    summary: typeof parsed.summary === 'string' ? parsed.summary : '',
    work_experience: asObjectList(parsed.work_experience).map(normalizeWorkExperience),
    education: asObjectList(parsed.education).map(normalizeEducation),
    skills: asStringList(parsed.skills),
    certifications: asObjectList(parsed.certifications).map(normalizeCertification),
    projects: asObjectList(parsed.projects).map(normalizeProject),
    achievements: asStringList(parsed.achievements),
    publications: asObjectList(parsed.publications).map(normalizePublication),
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
 * Result of a section save. A 422 is a normal outcome of an editor that lets
 * the user type freely, so it is returned as data rather than thrown: the
 * caller maps `errors` onto the inputs that caused them.
 */
export type ProfileUpdateResult =
  | { ok: true; profile: Profile }
  | {
      ok: false
      status?: number
      /** The toast sentence — `detail`, or a transport-level fallback. */
      message: string
      /** Field-level complaints; empty for anything that is not a 422. */
      errors: ProfileFieldError[]
    }

/** Reads the `errors` array off a 422 body, ignoring anything malformed. */
function readFieldErrors(error: unknown): ProfileFieldError[] {
  const body = apiErrorBody<ProfileUpdateErrorResponse>(error)
  if (!body || !Array.isArray(body.errors)) return []
  return body.errors.filter(
    (item): item is ProfileFieldError =>
      !!item &&
      typeof item === 'object' &&
      typeof item.field === 'string' &&
      typeof item.message === 'string',
  )
}

/**
 * `PATCH /profile` for one section, with the 422 kept as a value.
 *
 * The throwing `updateProfile` above stays for callers that only care whether
 * it worked; the profile editor needs the field errors, and an exception is a
 * poor carrier for a list of them.
 */
export async function updateProfileSection(
  patch: Partial<ParsedProfile>,
): Promise<ProfileUpdateResult> {
  try {
    return { ok: true, profile: await updateProfile(patch) }
  } catch (error) {
    return {
      ok: false,
      status: apiErrorStatus(error),
      message: apiErrorMessage(
        error,
        'We could not save that change. Please try again.',
      ),
      errors: readFieldErrors(error),
    }
  }
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

/* ------------------------------------------------------------------ */
/* Supplementary file import                                           */
/* ------------------------------------------------------------------ */

/** Extensions `POST /profile/import` accepts, in the order the copy lists them. */
export const IMPORT_EXTENSIONS = [
  '.xlsx',
  '.csv',
  '.docx',
  '.pdf',
  '.txt',
  '.md',
  '.json',
] as const

/** The `accept` attribute for the import file picker. */
export const IMPORT_ACCEPT = IMPORT_EXTENSIONS.join(',')

/** Same 10MB ceiling the backend enforces, checked before the upload starts. */
export const IMPORT_MAX_BYTES = 10 * 1024 * 1024

/**
 * A spreadsheet is read *and* merged by the model, which is a longer job than
 * a resume parse: the file is extracted, then compared entry by entry against
 * the stored profile. Well over the 40 seconds the slow case takes.
 */
export const IMPORT_TIMEOUT_MS = 600_000

/**
 * POST /profile/import — multipart upload that returns a merge *preview*.
 *
 * Nothing is saved: the response is a whole proposed `parsed_json` plus the
 * per-entry changes that produced it, which the review screen renders and
 * `applyProfileImport` writes back a section at a time. Throws on failure so
 * the uploader can show the message and let the user try another file; a retry
 * would bill a second read of a file that already cost 40 seconds, so this is
 * deliberately outside the automatic retry in services/api.
 */
export async function importProfileFile(
  file: File,
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<ImportProposal> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<ImportProposal>('/profile/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: IMPORT_TIMEOUT_MS,
    onUploadProgress,
  })
  const summary = data?.summary
  return {
    ...data,
    // Held as-is and never rendered; `applyProfileImport` hands it straight
    // back so the applied profile's raw_text can carry the imported source.
    document_text: typeof data?.document_text === 'string' ? data.document_text : null,
    proposal: normalizeParsedProfile(data?.proposal),
    changes: Array.isArray(data?.changes) ? data.changes : [],
    summary: {
      added: summary?.added ?? 0,
      updated: summary?.updated ?? 0,
      unchanged: summary?.unchanged ?? 0,
      removed: summary?.removed ?? 0,
      sections:
        summary?.sections && typeof summary.sections === 'object'
          ? summary.sections
          : {},
    },
    source: {
      // The server sends the filename it was given; falling back to the local
      // one keeps the review header naming the file the user actually picked.
      filename: data?.source?.filename ?? file.name,
      kind: data?.source?.kind ?? '',
      sheets: Array.isArray(data?.source?.sheets) ? data.source.sheets : [],
    },
  }
}

/**
 * POST /profile/import/apply — writes the chosen sections of a proposal.
 *
 * The whole proposal goes back, not just the picked sections, because the
 * server is the one that decides what each section's final value is; `sections`
 * is the permission list. Only those sections are replaced, the rest are left
 * exactly as they were.
 *
 * A 422 is kept as a value rather than thrown, the same way section saves are:
 * the review screen renders the messages above the cards and stays put.
 */
export async function applyProfileImport(
  parsedJson: ParsedProfile,
  sections: ProfileSectionKey[],
  filename?: string | null,
  documentText?: string | null,
): Promise<ProfileUpdateResult> {
  try {
    const body: ImportApplyRequest = {
      parsed_json: parsedJson,
      sections,
      filename: filename ?? null,
      // Echoed back from the import response: the server kept nothing between
      // the two calls, and this is what it appends to `raw_text`.
      document_text: documentText ?? null,
    }
    const { data } = await api.post<Profile>('/profile/import/apply', body)
    return { ok: true, profile: normalizeProfile(data) }
  } catch (error) {
    return {
      ok: false,
      status: apiErrorStatus(error),
      message: apiErrorMessage(
        error,
        'We could not apply that import. Please try again.',
      ),
      errors: readFieldErrors(error),
    }
  }
}
