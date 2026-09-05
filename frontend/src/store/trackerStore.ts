import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ResumeType, TrackerEntry, TrackerStatus } from '../types'

/**
 * All tracker entries. Persisted to localStorage.
 *
 * Phase 6 only needs enough of this store to keep the tracker honest the
 * moment a chat is created: `POST /chats` opens a tracker entry server-side,
 * so the sidebar mirrors it locally through `addEntry` rather than making the
 * user reload to see it. Fetching, filtering and status changes are Phase 8.
 */
export interface TrackerState {
  entries: TrackerEntry[]
  filter: TrackerStatus | 'all'
  isLoading: boolean
  error: string | null
  setEntries: (entries: TrackerEntry[]) => void
  /** Inserts newest-first, replacing any existing entry for the same chat. */
  addEntry: (entry: TrackerEntry) => void
  updateEntry: (chatId: string, patch: Partial<TrackerEntry>) => void
  removeEntry: (chatId: string) => void
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
        set((state) => ({
          entries: [
            entry,
            ...state.entries.filter((row) => row.chat_id !== entry.chat_id),
          ],
        })),

      updateEntry: (chatId, patch) =>
        set((state) => ({
          entries: state.entries.map((entry) =>
            entry.chat_id === chatId ? { ...entry, ...patch } : entry,
          ),
        })),

      removeEntry: (chatId) =>
        set((state) => ({
          entries: state.entries.filter((entry) => entry.chat_id !== chatId),
        })),

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
    {
      name: 'applify-tracker',
      // Bumped for the Phase 6 entry shape (nullable title/company, optional
      // user_id, and "tailored" rather than "ai_tailored"). Anything older is
      // dropped: the Phase 8 fetch is cheaper than reshaping a stale blob.
      version: 2,
      migrate: () => ({ entries: [] }),
      partialize: (state) => ({ entries: state.entries }),
    },
  ),
)

export default useTrackerStore
