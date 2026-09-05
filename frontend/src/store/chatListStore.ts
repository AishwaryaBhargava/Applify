import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiErrorMessage } from '../services/api'
import * as chatsService from '../services/chats'
import { useTrackerStore } from './trackerStore'
import type { JobChat, TrackerEntry } from '../types'

/** The optimistic tracker row mirroring the one `POST /chats` just opened. */
function trackerEntryFor(chat: JobChat): TrackerEntry {
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
  createChat: (
    title: string,
    company: string,
    jdText: string,
  ) => Promise<JobChat | null>
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

      createChat: async (title, company, jdText) => {
        set({ error: null })
        try {
          const chat = await chatsService.createChat({
            title: title.trim(),
            company: company.trim() || null,
            jd_text: jdText.trim() || null,
          })
          get().addChat(chat)
          // The backend opened a tracker entry in the same transaction; mirror
          // it now so the tracker is right without a reload.
          useTrackerStore.getState().addEntry(trackerEntryFor(chat))
          return chat
        } catch (error) {
          set({
            error: apiErrorMessage(error, 'Could not create that job chat.'),
          })
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
          set({
            chats: previous,
            error: apiErrorMessage(error, 'Could not delete that job chat.'),
          })
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
