import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiErrorMessage } from '../services/api'
import { getProfile, getProfileGaps, updateProfile } from '../services/profile'
import type { ParsedProfile, Profile, ProfileGap, ProfileSectionKey } from '../types'

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

  setProfile: (profile: Profile | null) => void
  setGaps: (gaps: ProfileGap[]) => void
  fetchProfile: () => Promise<void>
  fetchGaps: () => Promise<void>
  /**
   * Replaces one section wholesale. Optimistic: local state moves first, the
   * server-confirmed profile replaces it on success, and the previous value is
   * restored on failure.
   *
   * Returns null on success, or the error message to show inline.
   */
  updateSection: <K extends ProfileSectionKey>(
    section: K,
    value: ParsedProfile[K],
  ) => Promise<string | null>
  dismissGap: (gapId: string) => void
  /** Clears every dismissal, so a re-uploaded profile nudges again. */
  resetDismissals: () => void
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
        const previous = get().profile
        if (!previous) return 'Upload a resume before editing your profile.'

        set({
          isSaving: true,
          error: null,
          profile: {
            ...previous,
            parsed_json: { ...previous.parsed_json, [section]: value },
          },
        })

        try {
          const saved = await updateProfile({ [section]: value })
          set({ profile: saved, isSaving: false, error: null })
          // Filling a section can clear its nudge (or reveal a new thin one).
          await get().fetchGaps()
          return null
        } catch (error) {
          const message = apiErrorMessage(
            error,
            'We could not save that change. Please try again.',
          )
          // Roll the store back to the last server-confirmed profile. The
          // section editor keeps its own draft, so the user's typing survives.
          set({ profile: previous, isSaving: false, error: message })
          return message
        }
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

      reset: () =>
        set({
          profile: null,
          gaps: [],
          isLoading: false,
          isSaving: false,
          error: null,
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

export default useProfileStore
