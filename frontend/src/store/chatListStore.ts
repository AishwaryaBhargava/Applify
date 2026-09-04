import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { JobChat } from '../types'

/** All user chats, used to render the sidebar list. Persisted to localStorage. */
export interface ChatListState {
  chats: JobChat[]
  isLoading: boolean
  error: string | null
  setChats: (chats: JobChat[]) => void
  addChat: (chat: JobChat) => void
  removeChat: (chatId: string) => void
  fetchChats: () => Promise<void>
  reset: () => void
}

export const useChatListStore = create<ChatListState>()(
  persist(
    (set) => ({
      chats: [],
      isLoading: false,
      error: null,

      setChats: (chats) => set({ chats }),
      addChat: (chat) => set((state) => ({ chats: [chat, ...state.chats] })),
      removeChat: (chatId) =>
        set((state) => ({
          chats: state.chats.filter((chat) => chat.id !== chatId),
        })),

      // TODO(Phase 6): call services/chats.listChats
      fetchChats: async () => {},

      reset: () => set({ chats: [], isLoading: false, error: null }),
    }),
    { name: 'applify-chat-list' },
  ),
)
