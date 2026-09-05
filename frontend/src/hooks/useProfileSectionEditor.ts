import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  SECTION_ERROR_KEY,
  sectionsEqual,
  stripBlankEntries,
  toErrorMap,
  validateSection,
  type SectionErrorMap,
} from '../lib/profileValidation'
import { useProfileStore } from '../store/profileStore'
import { pushToast } from '../store/toastStore'
import type { SectionSaveStatus } from '../components/profile/ProfileSection'
import type { ParsedProfile, ProfileSectionKey } from '../types'

/** How long "Saved" stays up before fading out. */
const SAVED_FLASH_MS = 1500

/** Toast shown when the client-side rules reject a save before it is sent. */
export const VALIDATION_TOAST = 'Fill in the required fields'

/** The note shown when a save quietly dropped rows the user never filled in. */
export const BLANKS_REMOVED_NOTE = 'Empty rows were removed'

export interface SectionEditor<K extends ProfileSectionKey> {
  /** The last value the server confirmed — what Discard goes back to. */
  saved: ParsedProfile[K]
  /** What the inputs render: the local draft, which may be ahead of `saved`. */
  draft: ParsedProfile[K]
  isEditing: boolean
  /** True when the draft differs from `saved` in any way that would be saved. */
  isDirty: boolean
  /**
   * Field errors keyed `"<index>.<field>"`, or `"section"` for a problem that
   * is not about one row. Populated by the client-side rules or by a 422 —
   * both produce the same shape.
   */
  errors: SectionErrorMap
  status: SectionSaveStatus
  /** A one-off note under the header ("Empty rows were removed"). */
  note: string | null
  /** Enters edit mode on a fresh copy of the saved value. */
  beginEdit: () => void
  /** Local only. Never touches the network — that is what `save` is for. */
  setDraft: (next: ParsedProfile[K]) => void
  save: () => Promise<void>
  /** Throws the draft away and leaves edit mode. */
  discard: () => void
}

/**
 * Edit state for one profile section: a draft, explicit Save and Discard, and
 * the same validation the backend runs, mirrored client-side.
 *
 * This used to save on blur, on a 400ms debounce, and flush whatever was
 * pending on unmount. That is a fine model for a field that cannot be wrong and
 * a poor one for this form: `PATCH /profile` requires a title *and* a company
 * on a role, so tabbing out of a half-typed row fired a request that could only
 * fail, and the row a user added and had not filled in yet was dropped by the
 * server on the way past. Saving is now something the user asks for, once, when
 * the row is complete — and it is checked here first, so an incomplete row
 * costs no request at all.
 *
 * Nothing here writes to the store until the user presses Save, so a draft is
 * never confused with data.
 *
 * @param section The `parsed_json` key this editor owns.
 * @param value The server-confirmed value for that section.
 */
export function useProfileSectionEditor<K extends ProfileSectionKey>(
  section: K,
  value: ParsedProfile[K],
): SectionEditor<K> {
  const updateSection = useProfileStore((state) => state.updateSection)
  const markSectionDirty = useProfileStore((state) => state.markSectionDirty)

  const [draft, setDraftState] = useState<ParsedProfile[K]>(value)
  const [isEditing, setIsEditing] = useState(false)
  const [status, setStatus] = useState<SectionSaveStatus>('idle')
  const [errors, setErrors] = useState<SectionErrorMap>({})
  const [note, setNote] = useState<string | null>(null)

  const flashRef = useRef<number | null>(null)
  const savingRef = useRef(false)

  // Adopt the server value whenever the user is not in the middle of an edit.
  // While editing, the draft is the truth on screen and a refetch must not
  // reach in and rewrite what someone is typing.
  useEffect(() => {
    if (!isEditing) setDraftState(value)
  }, [value, isEditing])

  const isDirty = isEditing && !sectionsEqual(draft, value)

  // The sidebar's navigation guard reads this out of the store; the effect is
  // what keeps the store's view of "is anything unsaved" honest, including on
  // unmount, when the draft goes away with the page.
  useEffect(() => {
    markSectionDirty(section, isDirty)
  }, [section, isDirty, markSectionDirty])

  useEffect(
    () => () => {
      markSectionDirty(section, false)
      if (flashRef.current) window.clearTimeout(flashRef.current)
    },
    [section, markSectionDirty],
  )

  const beginEdit = useCallback(() => {
    if (flashRef.current) window.clearTimeout(flashRef.current)
    setDraftState(value)
    setErrors({})
    setNote(null)
    setStatus('idle')
    setIsEditing(true)
  }, [value])

  const setDraft = useCallback((next: ParsedProfile[K]) => {
    setDraftState(next)
    // Typing in a box that is complaining should stop it complaining; the next
    // Save re-runs every rule anyway.
    setErrors((current) => (Object.keys(current).length ? {} : current))
    setStatus((current) => (current === 'error' ? 'idle' : current))
  }, [])

  const discard = useCallback(() => {
    if (flashRef.current) window.clearTimeout(flashRef.current)
    setDraftState(value)
    setErrors({})
    setNote(null)
    setStatus('idle')
    setIsEditing(false)
  }, [value])

  const save = useCallback(async () => {
    if (savingRef.current) return
    if (flashRef.current) window.clearTimeout(flashRef.current)

    // A row with nothing in it is one the user added and never filled in. The
    // backend drops it silently; dropping it here as well means the request
    // and the screen agree about what was saved, and the indexes in a 422 line
    // up with the rows that are still on display.
    const { value: cleaned, removed } = stripBlankEntries(section, draft)
    if (removed > 0) {
      setDraftState(cleaned)
      setNote(BLANKS_REMOVED_NOTE)
    } else {
      setNote(null)
    }

    const found = validateSection(section, cleaned)
    if (found.length > 0) {
      setErrors(toErrorMap(found))
      setStatus('error')
      pushToast(VALIDATION_TOAST, 'error')
      return
    }

    savingRef.current = true
    setErrors({})
    setStatus('saving')

    const result = await updateSection(section, cleaned)
    savingRef.current = false

    if (result.ok) {
      const next = result.profile.parsed_json[section]
      setDraftState(next)
      setErrors({})
      setIsEditing(false)
      setStatus('saved')
      flashRef.current = window.setTimeout(() => setStatus('idle'), SAVED_FLASH_MS)
      return
    }

    // Failed: the draft stays exactly as typed and edit mode stays open, so
    // the user can fix the field rather than retype the row.
    setStatus('error')
    const fieldErrors = result.errors.filter((error) => error.section === section)
    if (fieldErrors.length > 0) {
      setErrors(toErrorMap(fieldErrors))
    } else {
      // A 422 with no usable `errors` (pydantic's own shape), or a transport
      // failure: one line above the section is the best we can do.
      setErrors({ [SECTION_ERROR_KEY]: result.message })
    }
  }, [section, draft, updateSection])

  return useMemo(
    () => ({
      saved: value,
      draft,
      isEditing,
      isDirty,
      errors,
      status,
      note,
      beginEdit,
      setDraft,
      save,
      discard,
    }),
    [
      value,
      draft,
      isEditing,
      isDirty,
      errors,
      status,
      note,
      beginEdit,
      setDraft,
      save,
      discard,
    ],
  )
}

export default useProfileSectionEditor
