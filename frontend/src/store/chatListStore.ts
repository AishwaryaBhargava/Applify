import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiErrorMessage } from '../services/api'
import * as chatsService from '../services/chats'
import { pushToast } from './toastStore'
import { useTrackerStore } from './trackerStore'
import type { JobChat, TrackerEntry } from '../types'

/**
 * What the new-chat form collects. `title` and `jdText` are what the chat
 * itself needs; the rest land on the tracker entry `POST /chats` opens in the
 * same transaction.
 */
export interface NewChatInput {
  title: string
  company: string
  jdText: string
  jobUrl?: string
  location?: string
  source?: string
}

/** '' from an untouched optional input means "not set", which is null. */
function orNull(value: string | undefined): string | null {
  const trimmed = (value ?? '').trim()
  return trimmed || null
}

/** The optimistic tracker row mirroring the one `POST /chats` just opened. */
function trackerEntryFor(chat: JobChat, input: NewChatInput): TrackerEntry {
  return {
    // The real row id lives on the server; the Phase 8 fetch replaces this.
    // The prefix makes an unsynced row obvious if one shows up in a log.
    id: `local:${chat.id}`,
    chat_id: chat.id,
    // Both names, as GET /tracker sends them: `job_title` is the server's,
    // `title` the one this store has always written.
    job_title: chat.title,
    title: chat.title,
    company: chat.company,
    date_added: chat.created_at,
    analysis_type: chat.analysis_type,
    status: 'not_applied',
    resume_type: chat.resume_type,
    fit_score: null,
    created_at: chat.created_at,
    updated_at: chat.created_at,
    // Mirrored from the form rather than guessed at: the server copied exactly
    // these three onto the row it just wrote, and the next GET /tracker
    // replaces the lot anyway.
    job_url: orNull(input.jobUrl),
    location: orNull(input.location),
    source: orNull(input.source),
    salary: null,
    applied_at: null,
    next_action: null,
    next_action_date: null,
    notes: null,
    priority: null,
    days_since_applied: null,
    next_action_due: false,
  }
}

/**
 * Every job chat the user has — the sidebar list. Persisted to localStorage so
 * the list paints immediately on a reload and is reconciled by `fetchChats`.
 */
export interface ChatListState {
  chats: JobChat[]
  isLoading: boolean
  error: string | null

  setChats: (chats: JobChat[]) => void
  addChat: (chat: JobChat) => void
  removeChat: (chatId: string) => void
  /** Merges server-known fields: has_analysis, analysis_type, resume_type. */
  updateChat: (chatId: string, patch: Partial<JobChat>) => void

  fetchChats: () => Promise<void>
  /**
   * Creates a chat and mirrors its tracker entry locally.
   * Resolves to the new chat, or null with `error` set on failure.
   */
  createChat: (input: NewChatInput) => Promise<JobChat | null>
  /** Optimistic delete; the row comes back if the request fails. */
  deleteChat: (chatId: string) => Promise<boolean>
  clearError: () => void
  reset: () => void
}

export const useChatListStore = create<ChatListState>()(
  persist(
    (set, get) => ({
      chats: [],
      isLoading: false,
      error: null,

      setChats: (chats) => set({ chats }),
      addChat: (chat) =>
        set((state) => ({
          chats: [chat, ...state.chats.filter((row) => row.id !== chat.id)],
        })),
      removeChat: (chatId) =>
        set((state) => ({
          chats: state.chats.filter((chat) => chat.id !== chatId),
        })),
      updateChat: (chatId, patch) =>
        set((state) => ({
          chats: state.chats.map((chat) =>
            chat.id === chatId ? { ...chat, ...patch } : chat,
          ),
        })),

      fetchChats: async () => {
        set({ isLoading: true, error: null })
        try {
          set({ chats: await chatsService.listChats(), isLoading: false })
        } catch (error) {
          // The persisted list stays on screen: a stale sidebar is more useful
          // than an empty one while the backend is unreachable.
          set({
            isLoading: false,
            error: apiErrorMessage(error, 'Could not load your job chats.'),
          })
        }
      },

      createChat: async (input) => {
        set({ error: null })
        try {
          const chat = await chatsService.createChat({
            title: input.title.trim(),
            company: input.company.trim() || null,
            jd_text: input.jdText.trim() || null,
            // Omitted entirely when empty rather than sent as null: a backend
            // from before these fields existed ignores unknown keys, but there
            // is no reason to make it read three of them on every create.
            ...(orNull(input.jobUrl) ? { job_url: orNull(input.jobUrl) } : {}),
            ...(orNull(input.location)
              ? { location: orNull(input.location) }
              : {}),
            ...(orNull(input.source) ? { source: orNull(input.source) } : {}),
          })
          get().addChat(chat)
          // The backend opened a tracker entry in the same transaction; mirror
          // it now so the tracker is right without a reload.
          useTrackerStore.getState().addEntry(trackerEntryFor(chat, input))
          return chat
        } catch (error) {
          const message = apiErrorMessage(
            error,
            'Could not create that job chat.',
          )
          // Shown inline under the modal's form as well: the toast is what
          // survives the modal being closed on the failure.
          set({ error: message })
          pushToast(message, 'error')
          return null
        }
      },

      deleteChat: async (chatId) => {
        const previous = get().chats
        get().removeChat(chatId)
        useTrackerStore.getState().removeEntry(chatId)
        try {
          await chatsService.deleteChat(chatId)
          return true
        } catch (error) {
          const message = apiErrorMessage(
            error,
            'Could not delete that job chat.',
          )
          // The row reappearing is the only other signal, and on its own that
          // reads as a bug in the list rather than a failed request.
          set({ chats: previous, error: message })
          pushToast(message, 'error')
          return false
        }
      },

      clearError: () => set({ error: null }),
      reset: () => set({ chats: [], isLoading: false, error: null }),
    }),
    {
      name: 'applify-chat-list',
      // Bumped for the Phase 6 JobChat shape (has_analysis, resume_type,
      // nullable company/jd_text). Older blobs are dropped and refetched.
      version: 2,
      migrate: () => ({ chats: [] }),
      partialize: (state) => ({ chats: state.chats }),
    },
  ),
)

export default useChatListStore
