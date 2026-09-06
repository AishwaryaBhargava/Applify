/**
 * Client-side mirror of the strict validation `PATCH /profile` runs.
 *
 * The backend is still the authority — every rule here exists there too, in
 * `backend/app/api/schemas/profile.py`, and a save that slips past this file is
 * caught by the 422 the editor renders anyway. The point of the mirror is that
 * the user finds out which box is empty *before* a request goes out, and that
 * the error shape is identical either way, so `useProfileSectionEditor` has one
 * code path for "the client said no" and "the server said no".
 *
 * Messages are copied from the backend verbatim, so a rule that only one of the
 * two enforces still reads the same in the UI.
 */

import type { ParsedProfile, ProfileFieldError, ProfileSectionKey } from '../types'

/* ------------------------------------------------------------------ */
/* Limits                                                              */
/* ------------------------------------------------------------------ */

/** Max lengths, matching the constants at the top of the backend's strict pass. */
export const PROFILE_LIMITS = {
  /** A job title or an organisation name. */
  NAME: 200,
  SUMMARY: 2000,
  /** Free-text description / details fields. */
  DETAIL: 2000,
  /** Dates stay free-form ("Jan 2022"); this only catches pasted prose. */
  DATE: 100,
  LINK: 500,
  HIGHLIGHTS: 20,
  HIGHLIGHT: 500,
  SKILL: 60,
  ACHIEVEMENT: 500,
  /** Short labels kept as free text: employment type, GPA, publication status. */
  LABEL: 100,
  /** A paper title: longer than a job title, shorter than an abstract. */
  TITLE: 500,
  AUTHORS: 1000,
  /** Coursework and honors are capped per entry, not per profile. */
  COURSEWORK_ITEMS: 50,
  AWARDS: 20,
} as const

/* ------------------------------------------------------------------ */
/* Error map                                                           */
/* ------------------------------------------------------------------ */

/**
 * Field errors for one section, keyed so an input can look up its own message
 * in constant time: `"1.company"` for the second entry's company box, and
 * `"section"` for anything that is not about a single row (an over-long
 * summary, too many highlights on a list as a whole).
 */
export type SectionErrorMap = Record<string, string>

/** The key a field's error lives under. */
export function errorKey(index: number | null | undefined, field: string): string {
  return index === null || index === undefined ? SECTION_ERROR_KEY : `${index}.${field}`
}

/**
 * The last segment of a possibly dotted field name — `links.github` -> `github`.
 *
 * Errors are keyed by the leaf, not the path, because that is how the backend
 * reports them: it validates a project's link group as its own object, so an
 * over-long URL comes back as `{"field": "github"}`. The editor reads the value
 * by path and its error by leaf, and both sources of truth line up.
 */
export function leafField(field: string): string {
  const parts = field.split('.')
  return parts[parts.length - 1]
}

/** The error-map key for one (possibly nested) entry field. */
export function entryErrorKey(index: number | null | undefined, field: string): string {
  return errorKey(index, leafField(field))
}

/** The key section-level (non-row) errors live under. */
export const SECTION_ERROR_KEY = 'section'

/**
 * Folds a list of structured errors into the map the inputs read.
 *
 * First error per key wins: the backend reports at most one problem per field
 * anyway, and stacking two messages under one input helps nobody.
 */
export function toErrorMap(errors: ProfileFieldError[]): SectionErrorMap {
  const map: SectionErrorMap = {}
  for (const error of errors) {
    const key = errorKey(error.index, error.field)
    if (!(key in map)) map[key] = error.message
  }
  return map
}

/* ------------------------------------------------------------------ */
/* Cleaning                                                            */
/* ------------------------------------------------------------------ */

/** `_clean_str`: a trimmed string, or null for anything empty or non-scalar. */
function cleanString(value: unknown): string | null {
  if (typeof value === 'number') return String(value)
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

/** `_clean_str_list`: non-empty items, de-duplicated case-insensitively. */
export function cleanStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const item of value) {
    const cleaned = cleanString(item)
    if (cleaned === null) continue
    const key = cleaned.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(cleaned)
  }
  return out
}

/**
 * True when nothing in this entry carries content — the row the editor added
 * and the user never filled in.
 *
 * Booleans do not count: a work entry where only the "I currently work here"
 * toggle is set still says nothing about the job. This is the one rule the
 * backend is *lenient* about, dropping such rows silently, so the editor drops
 * them too rather than sending rows it knows will vanish.
 */
export function isBlankEntry(entry: unknown): boolean {
  if (!entry || typeof entry !== 'object') return true
  for (const value of Object.values(entry as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      if (cleanStringList(value).length > 0) return false
    } else if (value !== null && typeof value === 'object') {
      // A nested group of fields — a project's `links` — is content like any
      // other. A project whose only filled-in box is its GitHub URL is a row
      // the user meant to add, not a stray one to drop.
      if (!isBlankEntry(value)) return false
    } else if (cleanString(value) !== null) {
      return false
    }
  }
  return true
}

/** Sections whose value is a list of entry objects. */
const ENTRY_SECTIONS = [
  'work_experience',
  'education',
  'certifications',
  'projects',
  'publications',
] as const

function isEntrySection(section: ProfileSectionKey): boolean {
  return (ENTRY_SECTIONS as readonly string[]).includes(section)
}

/**
 * Drops entries with nothing in them, so a stray row never reaches the server.
 *
 * Returns the count as well, because the section header says so out loud —
 * a row disappearing on save with no explanation is the exact failure this
 * whole rework is about.
 */
export function stripBlankEntries<K extends ProfileSectionKey>(
  section: K,
  value: ParsedProfile[K],
): { value: ParsedProfile[K]; removed: number } {
  if (!isEntrySection(section) || !Array.isArray(value)) {
    return { value, removed: 0 }
  }
  const kept = (value as unknown[]).filter((entry) => !isBlankEntry(entry))
  return {
    value: kept as ParsedProfile[K],
    removed: value.length - kept.length,
  }
}

/* ------------------------------------------------------------------ */
/* Rules                                                               */
/* ------------------------------------------------------------------ */

interface FieldRule {
  field: string
  /** The label the backend puts in the message ("Job title is required"). */
  label: string
  max: number
  required?: boolean
}

interface ListRule {
  field: string
  /** Singular, as the backend phrases it ("Each highlight must be..."). */
  label: string
  max: number
  maxItems?: number
}

const {
  NAME,
  DATE,
  DETAIL,
  LINK,
  HIGHLIGHT,
  HIGHLIGHTS,
  SKILL,
  LABEL,
  TITLE,
  AUTHORS,
  COURSEWORK_ITEMS,
  AWARDS,
} = PROFILE_LIMITS

/**
 * Per-section field rules, in the order the backend checks them.
 *
 * A dotted `field` reads one level into the entry — `links.github` is the
 * project's GitHub URL — and the error it produces is keyed by the same dotted
 * name, so the input that owns it finds its own message the same way every
 * other input does.
 */
const ENTRY_RULES: Record<string, FieldRule[]> = {
  work_experience: [
    { field: 'title', label: 'Job title', max: NAME, required: true },
    { field: 'company', label: 'Company', max: NAME, required: true },
    { field: 'location', label: 'Location', max: NAME },
    { field: 'employment_type', label: 'Employment type', max: LABEL },
    { field: 'start_date', label: 'Start date', max: DATE },
    { field: 'end_date', label: 'End date', max: DATE },
  ],
  education: [
    { field: 'degree', label: 'Degree', max: NAME },
    { field: 'field', label: 'Field of study', max: NAME },
    { field: 'institution', label: 'Institution', max: NAME, required: true },
    { field: 'start_date', label: 'Start date', max: DATE },
    { field: 'end_date', label: 'End date', max: DATE },
    { field: 'gpa', label: 'GPA', max: LABEL },
    { field: 'details', label: 'Details', max: DETAIL },
  ],
  certifications: [
    { field: 'name', label: 'Certification name', max: NAME, required: true },
    { field: 'issuer', label: 'Issuer', max: NAME },
    { field: 'year', label: 'Year', max: DATE },
    { field: 'expires', label: 'Expiry', max: DATE },
    { field: 'credential_url', label: 'Credential URL', max: LINK },
    { field: 'description', label: 'Description', max: DETAIL },
  ],
  projects: [
    { field: 'name', label: 'Project name', max: NAME, required: true },
    { field: 'description', label: 'Description', max: DETAIL },
    { field: 'link', label: 'Link', max: LINK },
    { field: 'start_date', label: 'Start date', max: DATE },
    { field: 'end_date', label: 'End date', max: DATE },
    { field: 'links.github', label: 'GitHub link', max: LINK },
    { field: 'links.live', label: 'Live link', max: LINK },
    { field: 'links.demo', label: 'Demo link', max: LINK },
  ],
  publications: [
    { field: 'title', label: 'Publication title', max: TITLE, required: true },
    // Author lists run long ("Smith J, Doe A, Nakamura K, ..."), so they get
    // their own ceiling rather than the 200-character name one.
    { field: 'authors', label: 'Authors', max: AUTHORS },
    { field: 'status', label: 'Status', max: LABEL },
    { field: 'year', label: 'Year', max: DATE },
    { field: 'url', label: 'Link', max: LINK },
  ],
}

/** The `string[]` fields nested inside an entry. */
const ENTRY_LIST_RULES: Record<string, ListRule[]> = {
  work_experience: [
    {
      field: 'highlights',
      label: 'highlight',
      max: HIGHLIGHT,
      maxItems: HIGHLIGHTS,
    },
    { field: 'awards', label: 'award', max: HIGHLIGHT, maxItems: AWARDS },
  ],
  education: [
    {
      field: 'coursework',
      label: 'course',
      max: NAME,
      maxItems: COURSEWORK_ITEMS,
    },
    // "honour", not "honor": the message has to read exactly as the backend's
    // does, and the backend spells it the British way.
    { field: 'honors', label: 'honour', max: NAME, maxItems: COURSEWORK_ITEMS },
  ],
  projects: [
    { field: 'technologies', label: 'technology', max: SKILL },
    {
      field: 'highlights',
      label: 'highlight',
      max: HIGHLIGHT,
      maxItems: HIGHLIGHTS,
    },
  ],
}

/**
 * Fields that must be filled in for the row to save, by section — what the
 * editor puts an asterisk and `aria-required` on.
 *
 * Education is the exception the UI has to spell out itself: the backend wants
 * an institution *plus* a degree or a field, and "one of these two" is not a
 * per-field required flag.
 */
export const REQUIRED_ENTRY_FIELDS: Record<string, string[]> = {
  work_experience: ['title', 'company'],
  education: ['institution'],
  certifications: ['name'],
  projects: ['name'],
  publications: ['title'],
}

/** Max length for one entry field, for the input's `maxLength` attribute. */
export function entryFieldMaxLength(
  section: string,
  field: string,
): number | undefined {
  return ENTRY_RULES[section]?.find((rule) => rule.field === field)?.max
}

/* ------------------------------------------------------------------ */
/* Validation                                                          */
/* ------------------------------------------------------------------ */

function addError(
  errors: ProfileFieldError[],
  section: string,
  index: number | null,
  field: string,
  message: string,
): void {
  errors.push({ section, index, field, message })
}

/**
 * Reads a field off an entry, following one level of dotted path.
 *
 * `readEntryField(project, 'links.github')` is the GitHub URL; a missing group
 * reads as absent rather than throwing, because a project stored before
 * `links` existed has no group at all.
 */
export function readEntryField(entry: unknown, field: string): unknown {
  if (!entry || typeof entry !== 'object') return undefined
  const [head, ...rest] = field.split('.')
  const value = (entry as Record<string, unknown>)[head]
  return rest.length === 0 ? value : readEntryField(value, rest.join('.'))
}

/** `_strict_str`: required-ness and length for one string field. */
function checkField(
  errors: ProfileFieldError[],
  item: Record<string, unknown>,
  rule: FieldRule,
  section: string,
  index: number,
): string | null {
  // Reported by leaf name, exactly as the backend reports it.
  const field = leafField(rule.field)
  const value = cleanString(readEntryField(item, rule.field))
  if (value === null) {
    if (rule.required) {
      addError(errors, section, index, field, `${rule.label} is required`)
    }
    return null
  }
  if (value.length > rule.max) {
    addError(
      errors,
      section,
      index,
      field,
      `${rule.label} must be ${rule.max} characters or less`,
    )
  }
  return value
}

/** `_strict_str_list`: only over-long items and over-long lists are errors. */
function checkList(
  errors: ProfileFieldError[],
  value: unknown,
  rule: ListRule,
  section: string,
  index: number | null,
): void {
  if (!Array.isArray(value)) return
  let tooLong = false
  const kept: string[] = []
  const seen = new Set<string>()
  for (const item of value) {
    const cleaned = cleanString(item)
    if (cleaned === null) continue
    if (cleaned.length > rule.max) {
      // One error per list, not one per item: the user gets the rule once.
      tooLong = true
      continue
    }
    const key = cleaned.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    kept.push(cleaned)
  }
  if (tooLong) {
    addError(
      errors,
      section,
      index,
      rule.field,
      `Each ${rule.label} must be ${rule.max} characters or less`,
    )
  }
  if (rule.maxItems !== undefined && kept.length > rule.maxItems) {
    addError(
      errors,
      section,
      index,
      rule.field,
      `Keep ${rule.field.replace(/_/g, ' ')} to ${rule.maxItems} or fewer`,
    )
  }
}

/**
 * Runs every rule the backend would run on one section.
 *
 * Blank entries are ignored rather than reported — call `stripBlankEntries`
 * first if the indexes in the result have to line up with what is on screen,
 * which is exactly what the editor does before it validates.
 *
 * @param section The `parsed_json` key being saved.
 * @param value The section's draft value.
 * @returns Every problem found, in the same shape the backend's 422 carries.
 */
export function validateSection<K extends ProfileSectionKey>(
  section: K,
  value: ParsedProfile[K],
): ProfileFieldError[] {
  const errors: ProfileFieldError[] = []

  if (section === 'summary') {
    const summary = cleanString(value)
    if (summary !== null && summary.length > PROFILE_LIMITS.SUMMARY) {
      addError(
        errors,
        section,
        null,
        'summary',
        `Summary must be ${PROFILE_LIMITS.SUMMARY} characters or less`,
      )
    }
    return errors
  }

  if (section === 'skills' || section === 'achievements') {
    checkList(
      errors,
      value,
      section === 'skills'
        ? { field: 'skills', label: 'skill', max: PROFILE_LIMITS.SKILL }
        : {
            field: 'achievements',
            label: 'achievement',
            max: PROFILE_LIMITS.ACHIEVEMENT,
          },
      section,
      null,
    )
    return errors
  }

  const rules = ENTRY_RULES[section] ?? []
  const listRules = ENTRY_LIST_RULES[section] ?? []
  const items = Array.isArray(value) ? (value as unknown[]) : []

  items.forEach((raw, index) => {
    if (!raw || typeof raw !== 'object' || isBlankEntry(raw)) return
    const item = raw as Record<string, unknown>
    const cleaned: Record<string, string | null> = {}
    for (const rule of rules) {
      cleaned[rule.field] = checkField(errors, item, rule, section, index)
    }
    // Either one says what was studied. Demanding both would reject "BSc" and
    // "Computer Science" alike, and resumes list them both ways.
    if (
      section === 'education' &&
      cleaned.degree === null &&
      cleaned.field === null
    ) {
      addError(
        errors,
        section,
        index,
        'degree',
        'Degree or field of study is required',
      )
    }
    for (const rule of listRules) {
      checkList(errors, item[rule.field], rule, section, index)
    }
  })

  return errors
}

/* ------------------------------------------------------------------ */
/* Dirty comparison                                                    */
/* ------------------------------------------------------------------ */

/**
 * A canonical rendering of a section value, used to decide whether the draft
 * has actually moved.
 *
 * Strings are trimmed and `null` reads the same as `''`, so clicking into an
 * empty box and out again is not "unsaved changes". Blank rows are *kept*: the
 * user added one on purpose and Discard should take it away again.
 */
function canonical(value: unknown): unknown {
  if (typeof value === 'string') return value.trim()
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(canonical)
  if (typeof value === 'object') {
    const source = value as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(source).sort()) out[key] = canonical(source[key])
    return out
  }
  return value
}

/** True when two section values are the same edit, ignoring whitespace noise. */
export function sectionsEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b))
}
