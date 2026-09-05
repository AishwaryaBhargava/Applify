import { useCallback, useEffect, useRef, useState } from 'react'
import { useProfileStore } from '../store/profileStore'
import type { SectionSaveStatus } from '../components/profile/ProfileSection'
import type { ParsedProfile, ProfileSectionKey } from '../types'

/**
 * Long enough that tabbing across a whole entry sends one PATCH instead of
 * one per field, short enough that the "Saved" flash still feels immediate.
 */
const SAVE_DEBOUNCE_MS = 400
/** How long "Saved" stays up before fading out. */
const SAVED_FLASH_MS = 1500

export interface SectionEditor<K extends ProfileSectionKey> {
  /** The value to render — the local draft, which may be ahead of the server. */
  draft: ParsedProfile[K]
  isEditing: boolean
  status: SectionSaveStatus
  error: string | null
  /** Replaces the whole section value and schedules a debounced save. */
  setDraft: (next: ParsedProfile[K]) => void
  /**
   * Changes the draft without saving — for edits that are not yet worth a
   * PATCH, such as adding a blank entry the user has not filled in. The
   * backend drops empty entries, so saving one would make the new card vanish
   * under the user's cursor.
   */
  setDraftLocal: (next: ParsedProfile[K]) => void
  toggleEdit: () => void
}

/**
 * Edit state for one profile section: a local draft, a debounced whole-section
 * save, and the status the section header renders.
 *
 * The draft is deliberately separate from the store. `updateSection` rolls the
 * store back when a PATCH fails; the draft does not, so a failed save leaves
 * the user's typing on screen to retry rather than silently reverting it.
 *
 * @param section The `parsed_json` key this editor owns.
 * @param value The server-confirmed value for that section.
 */
export function useProfileSectionEditor<K extends ProfileSectionKey>(
  section: K,
  value: ParsedProfile[K],
): SectionEditor<K> {
  const updateSection = useProfileStore((state) => state.updateSection)

  const [draft, setDraftState] = useState<ParsedProfile[K]>(value)
  const [isEditing, setIsEditing] = useState(false)
  const [status, setStatus] = useState<SectionSaveStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  /** True while a local edit has not yet been confirmed by the server. */
  const dirtyRef = useRef(false)
  const pendingRef = useRef<ParsedProfile[K] | null>(null)
  const debounceRef = useRef<number | null>(null)
  const flashRef = useRef<number | null>(null)

  // Adopt the server value, unless the user has an unsaved or failed edit in
  // flight — overwriting that would throw away their typing.
  useEffect(() => {
    if (!dirtyRef.current) setDraftState(value)
  }, [value])

  const flush = useCallback(async () => {
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    const next = pendingRef.current
    if (next === null) return
    pendingRef.current = null

    setStatus('saving')
    setError(null)

    const message = await updateSection(section, next)
    if (message) {
      setStatus('error')
      setError(message)
      return
    }

    dirtyRef.current = false
    setError(null)
    setStatus('saved')
    if (flashRef.current) window.clearTimeout(flashRef.current)
    flashRef.current = window.setTimeout(() => setStatus('idle'), SAVED_FLASH_MS)
  }, [section, updateSection])

  const setDraft = useCallback(
    (next: ParsedProfile[K]) => {
      dirtyRef.current = true
      pendingRef.current = next
      setDraftState(next)
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(() => {
        void flush()
      }, SAVE_DEBOUNCE_MS)
    },
    [flush],
  )

  const setDraftLocal = useCallback((next: ParsedProfile[K]) => {
    // Marked dirty so a later server response cannot wipe the new blank entry.
    dirtyRef.current = true
    setDraftState(next)
  }, [])

  const toggleEdit = useCallback(() => {
    // Leaving edit mode saves whatever is still pending straight away. The
    // blur that fires as the button is pressed has already queued it.
    if (isEditing) void flush()
    setIsEditing((editing) => !editing)
  }, [isEditing, flush])

  // A pending edit must not be lost to a navigation inside the debounce window.
  useEffect(
    () => () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
      if (flashRef.current) window.clearTimeout(flashRef.current)
      const next = pendingRef.current
      pendingRef.current = null
      if (next !== null) void updateSection(section, next)
    },
    [section, updateSection],
  )

  return { draft, isEditing, status, error, setDraft, setDraftLocal, toggleEdit }
}

export default useProfileSectionEditor
