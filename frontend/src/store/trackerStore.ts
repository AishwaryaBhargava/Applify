import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ResumeType, TrackerEntry, TrackerStatus } from '../types'

/** All tracker entries. Persisted to localStorage. */
export interface TrackerState {
  entries: TrackerEntry[]
  filter: TrackerStatus | 'all'
  isLoading: boolean
  error: string | null
  setEntries: (entries: TrackerEntry[]) => void
  addEntry: (entry: TrackerEntry) => void
  setFilter: (filter: TrackerStatus | 'all') => void
  setResumeType: (chatId: string, resumeType: ResumeType) => void
  fetchEntries: () => Promise<void>
  updateStatus: (chatId: string, status: TrackerStatus) => Promise<void>
  reset: () => void
}

export const useTrackerStore = create<TrackerState>()(
  persist(
    (set) => ({
      entries: [],
      filter: 'all',
      isLoading: false,
      error: null,

      setEntries: (entries) => set({ entries }),
      addEntry: (entry) =>
        set((state) => ({ entries: [entry, ...state.entries] })),
      setFilter: (filter) => set({ filter }),
      setResumeType: (chatId, resumeType) =>
        set((state) => ({
          entries: state.entries.map((entry) =>
            entry.chat_id === chatId
              ? { ...entry, resume_type: resumeType }
              : entry,
          ),
        })),

      // TODO(Phase 8): call services/tracker.listTrackerEntries
      fetchEntries: async () => {},
      // TODO(Phase 8): call services/tracker.updateTrackerStatus then update state
      updateStatus: async (_chatId, _status) => {},

      reset: () => set({ entries: [], isLoading: false, error: null }),
    }),
    { name: 'applify-tracker' },
  ),
)
