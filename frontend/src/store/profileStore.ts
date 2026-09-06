import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  getProfile,
  getProfileGaps,
  updateProfileSection,
  type ProfileUpdateResult,
} from '../services/profile'
import { pushToast } from './toastStore'
import type {
  ImportProposal,
  ParsedProfile,
  Profile,
  ProfileGap,
  ProfileSectionKey,
} from '../types'

/**
 * Dismissed nudges live under their own key rather than inside the persisted
 * store blob: they outlive a profile reset (signing out should not resurrect
 * nudges the user already waved away) and they are cleared deliberately, by
 * `resetDismissals`, when a new resume is uploaded.
 */
const DISMISSED_KEY = 'applify-dismissed-gaps'

function readDismissed(): string[] {
  try {
    const raw = window.localStorage.getItem(DISMISSED_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed.filter((id): id is string => typeof id === 'string')
      : []
  } catch {
    // Storage unavailable or corrupt: nudge as if nothing was dismissed.
    return []
  }
}

function writeDismissed(ids: string[]): void {
  try {
    window.localStorage.setItem(DISMISSED_KEY, JSON.stringify(ids))
  } catch {
    // Storage unavailable: the dismissal holds for this session only.
  }
}

/** Parsed profile data and enrichment state. Persisted to localStorage. */
export interface ProfileState {
  profile: Profile | null
  gaps: ProfileGap[]
  /** Gap ids the user has waved away. Cleared only on a fresh upload. */
  dismissedGapIds: string[]
  isLoading: boolean
  isSaving: boolean
  error: string | null
  /**
   * Sections with an unsaved draft on screen.
   *
   * Lives in the store rather than in the page so the sidebar — which is not a
   * child of the profile page — can ask "is there anything to lose?" before it
   * lets a navigation through. Never persisted: a draft does not survive a
   * reload, so a dirty flag that did would be a lie.
   */
  dirtySections: Set<ProfileSectionKey>
  /**
   * The merge preview `POST /profile/import` returned, waiting on the review
   * screen.
   *
   * Deliberately not persisted. It is a proposal, not data — reloading
   * /profile/import with a stale one from localStorage would offer to apply a
   * file the user uploaded days ago, so a refresh sends them back to /profile
   * instead and they upload again.
   */
  importProposal: ImportProposal | null

  setProfile: (profile: Profile | null) => void
  setGaps: (gaps: ProfileGap[]) => void
  fetchProfile: () => Promise<void>
  fetchGaps: () => Promise<void>
  /**
   * Replaces one section wholesale, on an explicit Save.
   *
   * Not optimistic and never throws: the server-confirmed profile is adopted on
   * success, and a failure returns the reason — including the field-level
   * `errors` of a 422 — for the section editor to render against its inputs.
   */
  updateSection: <K extends ProfileSectionKey>(
    section: K,
    value: ParsedProfile[K],
  ) => Promise<ProfileUpdateResult>
  /** Records (or clears) one section's unsaved-changes flag. */
  markSectionDirty: (section: ProfileSectionKey, dirty: boolean) => void
  /** Forgets every dirty flag — on leaving the page, or after a discard-all. */
  clearDirtySections: () => void
  dismissGap: (gapId: string) => void
  /** Clears every dismissal, so a re-uploaded profile nudges again. */
  resetDismissals: () => void
  /** Stages a merge preview for the review screen (null clears it). */
  setImportProposal: (proposal: ImportProposal | null) => void
  reset: () => void
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set, get) => ({
      profile: null,
      gaps: [],
      dismissedGapIds: readDismissed(),
      isLoading: false,
      isSaving: false,
      error: null,
      dirtySections: new Set<ProfileSectionKey>(),
      importProposal: null,

      setProfile: (profile) => set({ profile }),
      setGaps: (gaps) => set({ gaps }),

      fetchProfile: async () => {
        set({ isLoading: true, error: null })
        const result = await getProfile()
        if (result.status === 'ok') {
          set({ profile: result.profile, isLoading: false })
        } else if (result.status === 'missing') {
          set({ profile: null, gaps: [], isLoading: false })
        } else {
          set({ isLoading: false, error: result.message })
        }
      },

      fetchGaps: async () => {
        try {
          set({ gaps: await getProfileGaps() })
        } catch {
          // Gap detection is advisory. A failure leaves the last known nudges
          // in place rather than blocking the page with an error.
        }
      },

      updateSection: async (section, value) => {
        if (!get().profile) {
          return {
            ok: false,
            message: 'Upload a resume before editing your profile.',
            errors: [],
          }
        }

        set({ isSaving: true, error: null })
        const result = await updateProfileSection({ [section]: value })

        if (result.ok) {
          set({ profile: result.profile, isSaving: false, error: null })
          // Filling a section can clear its nudge (or reveal a new thin one).
          // Only ever after a save the server accepted.
          await get().fetchGaps()
          return result
        }

        // The stored profile was never touched — the save is explicit, so
        // there is no optimistic write to roll back, and the editor still
        // holds the draft the user typed.
        set({ isSaving: false, error: result.message })
        // A 422 is rendered against the offending inputs; a toast would say
        // the same thing twice. Anything else gets one, because the reason is
        // not visible anywhere near the section.
        if (result.status !== 422) pushToast(result.message, 'error')
        return result
      },

      markSectionDirty: (section, dirty) => {
        const current = get().dirtySections
        if (current.has(section) === dirty) return
        const next = new Set(current)
        if (dirty) next.add(section)
        else next.delete(section)
        set({ dirtySections: next })
      },

      clearDirtySections: () => {
        if (get().dirtySections.size === 0) return
        set({ dirtySections: new Set<ProfileSectionKey>() })
      },

      dismissGap: (gapId) => {
        const current = get().dismissedGapIds
        if (current.includes(gapId)) return
        const next = [...current, gapId]
        writeDismissed(next)
        set({ dismissedGapIds: next })
      },

      resetDismissals: () => {
        writeDismissed([])
        set({ dismissedGapIds: [] })
      },

      setImportProposal: (proposal) => set({ importProposal: proposal }),

      reset: () =>
        set({
          profile: null,
          gaps: [],
          isLoading: false,
          isSaving: false,
          error: null,
          dirtySections: new Set<ProfileSectionKey>(),
          importProposal: null,
        }),
    }),
    {
      name: 'applify-profile',
      // Bumped for the Phase 5 parsed_json shape. Anything older is dropped
      // rather than migrated: a refetch is cheaper and safer than reshaping a
      // stale blob written by a previous contract.
      version: 2,
      migrate: () => ({ profile: null, gaps: [] }),
      // Dismissals have their own key; transient flags are never persisted.
      partialize: (state) => ({ profile: state.profile, gaps: state.gaps }),
      // The dedicated dismissals key is the only source of truth for
      // dismissals, even if an older blob happens to carry the field.
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<ProfileState>),
        dismissedGapIds: current.dismissedGapIds,
      }),
    },
  ),
)

/**
 * Whether any profile section has an unsaved draft, readable from outside
 * React — the navigation guard runs inside a click handler in the sidebar,
 * which is nowhere near the profile page's component tree.
 */
export function hasUnsavedProfileChanges(): boolean {
  return useProfileStore.getState().dirtySections.size > 0
}

export default useProfileStore
