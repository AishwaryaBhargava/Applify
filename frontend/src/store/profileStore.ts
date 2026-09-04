import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ParsedProfile, Profile, ProfileGap } from '../types'

/** Parsed profile data and enrichment state. Persisted to localStorage. */
export interface ProfileState {
  profile: Profile | null
  gaps: ProfileGap[]
  dismissedGapIds: string[]
  isLoading: boolean
  error: string | null
  setProfile: (profile: Profile | null) => void
  setGaps: (gaps: ProfileGap[]) => void
  dismissGap: (gapId: string) => void
  fetchProfile: () => Promise<void>
  updateProfile: (patch: Partial<ParsedProfile>) => Promise<void>
  reset: () => void
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      profile: null,
      gaps: [],
      dismissedGapIds: [],
      isLoading: false,
      error: null,

      setProfile: (profile) => set({ profile }),
      setGaps: (gaps) => set({ gaps }),
      dismissGap: (gapId) =>
        set((state) => ({
          dismissedGapIds: state.dismissedGapIds.includes(gapId)
            ? state.dismissedGapIds
            : [...state.dismissedGapIds, gapId],
        })),

      // TODO(Phase 4/5): call services/profile.getProfile and getProfileGaps
      fetchProfile: async () => {},
      // TODO(Phase 5): call services/profile.updateProfile and merge the result
      updateProfile: async (_patch) => {},

      reset: () =>
        set({ profile: null, gaps: [], isLoading: false, error: null }),
    }),
    { name: 'applify-profile' },
  ),
)
