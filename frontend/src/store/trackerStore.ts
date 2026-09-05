import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiErrorMessage } from '../services/api'
import {
  listTrackerEntries,
  updateTrackerStatus,
} from '../services/tracker'
import { pushToast } from './toastStore'
import type { ResumeType, TrackerEntry, TrackerStatus } from '../types'

/**
 * Whether the app-load fetch has already run this session.
 *
 * The app shell remounts on every navigation between protected pages, so
 * without this the tracker would refetch each time the user moved between the
 * chat and their profile. The tracker page itself passes `force` and always
 * refetches.
 */
let hasFetched = false

/**
 * Every application in the tracker.
 *
 * Persisted to localStorage so the table paints immediately on a reload and is
 * then reconciled by `fetchEntries` — the same bargain the sidebar's chat list
 * makes. Two other stores write here without a fetch: `chatListStore` mirrors
 * the row `POST /chats` opens, and `chatStore` flips `resume_type` the moment
 * a tailored resume finishes streaming.
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
  /** GET /tracker. Skipped after the first call unless `force` is passed. */
  fetchEntries: (options?: { force?: boolean }) => Promise<void>
  /** Optimistic status change; the old status comes back if the PATCH fails. */
  updateStatus: (chatId: string, status: TrackerStatus) => Promise<boolean>
  clearError: () => void
  reset: () => void
}

export const useTrackerStore = create<TrackerState>()(
  persist(
    (set, get) => ({
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

      /**
       * Replaces the local rows with the server's.
       *
       * On failure the persisted rows stay on screen — a slightly stale table
       * is more useful than an empty one — and `error` drives a banner above
       * it rather than replacing it.
       */
      fetchEntries: async ({ force = false } = {}) => {
        if (!force && hasFetched) return
        if (get().isLoading) return

        hasFetched = true
        set({ isLoading: true, error: null })
        try {
          set({ entries: await listTrackerEntries(), isLoading: false })
        } catch (error) {
          set({
            isLoading: false,
            error: apiErrorMessage(error, 'Could not load your applications.'),
          })
        }
      },

      /**
       * Moves one application to a new status.
       *
       * Written locally first so the picker never lags the click, then rolled
       * back to the exact previous status if the PATCH fails — with a toast,
       * because a status that silently reverted would be read as a bug in the
       * dropdown rather than a failed request.
       */
      updateStatus: async (chatId, status) => {
        const previous = get().entries.find((entry) => entry.chat_id === chatId)
        if (!previous || previous.status === status) return true

        get().updateEntry(chatId, { status })
        try {
          const updated = await updateTrackerStatus(chatId, status)
          // The server's row also carries a fresh updated_at and, on an entry
          // the sidebar created optimistically, its real id.
          get().updateEntry(chatId, updated)
          return true
        } catch (error) {
          get().updateEntry(chatId, { status: previous.status })
          pushToast(
            apiErrorMessage(error, 'That status change did not save.'),
            'error',
          )
          return false
        }
      },

      clearError: () => set({ error: null }),

      reset: () => {
        hasFetched = false
        set({ entries: [], filter: 'all', isLoading: false, error: null })
      },
    }),
    {
      name: 'applify-tracker',
      // Bumped for the Phase 8 entry shape (job_title, date_added, fit_score
      // alongside the Phase 6 names). Anything older is dropped: the fetch is
      // cheaper than reshaping a stale blob.
      version: 3,
      migrate: () => ({ entries: [] }),
      partialize: (state) => ({ entries: state.entries }),
    },
  ),
)

export default useTrackerStore
