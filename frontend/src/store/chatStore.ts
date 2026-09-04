import { create } from 'zustand'
import type {
  Analysis,
  AnalysisType,
  ChatMessage,
  GeneratedOutput,
  JobChat,
} from '../types'

/**
 * Active chat state: messages, analysis, streaming state, generated outputs.
 * Not persisted — the active chat is always re-fetched from the backend.
 */
export interface ChatState {
  activeChat: JobChat | null
  messages: ChatMessage[]
  analysis: Analysis | null
  outputs: GeneratedOutput[]
  isStreaming: boolean
  streamingContent: string
  isLoading: boolean
  error: string | null
  setActiveChat: (chat: JobChat | null) => void
  setMessages: (messages: ChatMessage[]) => void
  appendMessage: (message: ChatMessage) => void
  appendStreamToken: (token: string) => void
  setStreaming: (isStreaming: boolean) => void
  setAnalysis: (analysis: Analysis | null) => void
  addOutput: (output: GeneratedOutput) => void
  loadChat: (chatId: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  runAnalysis: (type: AnalysisType) => Promise<void>
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeChat: null,
  messages: [],
  analysis: null,
  outputs: [],
  isStreaming: false,
  streamingContent: '',
  isLoading: false,
  error: null,

  setActiveChat: (activeChat) => set({ activeChat }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  appendStreamToken: (token) =>
    set((state) => ({ streamingContent: state.streamingContent + token })),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setAnalysis: (analysis) => set({ analysis }),
  addOutput: (output) =>
    set((state) => ({ outputs: [...state.outputs, output] })),

  // TODO(Phase 6): call services/chats.getChat and hydrate the store
  loadChat: async (_chatId) => {},
  // TODO(Phase 6): call services/messages.sendMessage and stream via useStream
  sendMessage: async (_content) => {},
  // TODO(Phase 6): call services/analysis.runAnalysis
  runAnalysis: async (_type) => {},

  reset: () =>
    set({
      activeChat: null,
      messages: [],
      analysis: null,
      outputs: [],
      isStreaming: false,
      streamingContent: '',
      isLoading: false,
      error: null,
    }),
}))
