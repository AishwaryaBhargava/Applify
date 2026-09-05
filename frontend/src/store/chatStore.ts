import { create } from 'zustand'
import { apiErrorMessage, apiErrorStatus } from '../services/api'
import { runAnalysis as runAnalysisRequest } from '../services/analysis'
import { getChat } from '../services/chats'
import { listMessages, streamMessage } from '../services/messages'
import { useChatListStore } from './chatListStore'
import { useTrackerStore } from './trackerStore'
import type {
  Analysis,
  AnalysisType,
  ChatMessage,
  GeneratedOutput,
  JobChat,
  MessageKind,
  ThreadMessage,
} from '../types'

/** The 409 body `POST /chats/{id}/analyze` returns when there is no profile. */
export const NO_PROFILE_STATUS = 409

/**
 * The in-flight stream's abort handle. Module scope rather than store state:
 * an AbortController is not serialisable and nothing renders from it.
 */
let controller: AbortController | null = null

/**
 * Incremented on every `loadChat`. A response whose token is stale — the user
 * clicked a second chat while the first was still loading — is discarded
 * instead of overwriting the chat now on screen.
 */
let loadToken = 0

/** A unique id for a client-side message, with a fallback for old browsers. */
function localId(prefix: string): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${random}`
}

/** Strips the client-only flags so a server message replaces a local one cleanly. */
function fromServer(messages: ChatMessage[]): ThreadMessage[] {
  return messages.map((message) => ({ ...message }))
}

/**
 * The chat currently on screen: its messages, its analysis, and the state of
 * any stream in flight. Deliberately not persisted — a chat is always rebuilt
 * from `GET /chats/{id}`, so a reload can never show a message the server does
 * not have or re-run an analysis it already stored.
 */
export interface ChatState {
  activeChat: JobChat | null
  messages: ThreadMessage[]
  analysis: Analysis | null
  outputs: GeneratedOutput[]

  isLoadingChat: boolean
  isAnalyzing: boolean
  isStreaming: boolean
  /** Id of the assistant message currently being streamed into. */
  streamingMessageId: string | null

  /** Load / delete failures for the chat as a whole. */
  error: string | null
  /** Failures of the last analyze request, shown inside the analysis area. */
  analysisError: string | null
  /** HTTP status of that failure. 409 means "upload your resume first". */
  analysisErrorStatus: number | null

  setActiveChat: (chat: JobChat | null) => void
  setMessages: (messages: ThreadMessage[]) => void
  setAnalysis: (analysis: Analysis | null) => void
  addOutput: (output: GeneratedOutput) => void

  loadChat: (chatId: string) => Promise<void>
  runAnalysis: (type: AnalysisType, force?: boolean) => Promise<void>

  appendUserMessage: (content: string) => void
  startAssistantMessage: (messageId: string, kind: MessageKind) => void
  appendToken: (token: string) => void
  finalizeAssistantMessage: (messageId: string, content: string) => void
  markError: (
    message: string,
    partialContent?: string,
    messageId?: string,
  ) => void

  sendMessage: (content: string) => Promise<void>
  /** Re-sends the last user turn after a failed or stopped stream. */
  retryLast: () => Promise<void>
  abortStream: () => void

  clearError: () => void
  clearAnalysisError: () => void
  reset: () => void
}

const emptyChat = {
  activeChat: null,
  messages: [] as ThreadMessage[],
  analysis: null,
  outputs: [] as GeneratedOutput[],
  isLoadingChat: false,
  isAnalyzing: false,
  isStreaming: false,
  streamingMessageId: null,
  error: null,
  analysisError: null,
  analysisErrorStatus: null,
}

export const useChatStore = create<ChatState>((set, get) => ({
  ...emptyChat,

  setActiveChat: (activeChat) => set({ activeChat }),
  setMessages: (messages) => set({ messages }),
  setAnalysis: (analysis) => set({ analysis }),
  addOutput: (output) =>
    set((state) => ({ outputs: [...state.outputs, output] })),

  clearError: () => set({ error: null }),
  clearAnalysisError: () => set({ analysisError: null, analysisErrorStatus: null }),

  /**
   * Rebuilds the page from `GET /chats/{id}`: chat, full history, and the
   * stored analysis. Any stream still running for the previous chat is aborted
   * first so its tokens cannot land in the new thread.
   */
  loadChat: async (chatId) => {
    get().abortStream()
    const token = ++loadToken
    const switching = get().activeChat?.id !== chatId

    set({
      isLoadingChat: true,
      error: null,
      analysisError: null,
      analysisErrorStatus: null,
      // Keep the current thread visible when reloading the same chat; clear it
      // when moving to a different one so the old messages never flash.
      ...(switching
        ? { messages: [], analysis: null, activeChat: null, outputs: [] }
        : {}),
    })

    try {
      const detail = await getChat(chatId)
      if (token !== loadToken) return

      const { messages, analysis, ...chat } = detail
      set({
        activeChat: chat,
        messages: fromServer(messages),
        analysis,
        isLoadingChat: false,
      })
      // The sidebar row may predate the analysis; keep the two in step.
      useChatListStore.getState().updateChat(chatId, chat)
    } catch (error) {
      if (token !== loadToken) return
      const status = apiErrorStatus(error)
      set({
        isLoadingChat: false,
        error:
          status === 404
            ? 'That job chat no longer exists.'
            : apiErrorMessage(error, 'Could not load that job chat.'),
      })
      // A 404 means it was deleted elsewhere; drop it from the sidebar too.
      if (status === 404) useChatListStore.getState().removeChat(chatId)
    }
  },

  /**
   * Runs the analysis and reloads the thread.
   *
   * The backend appends an assistant message rendering the analysis (plus its
   * one proactive suggestion) inside the same transaction, so the messages are
   * refetched rather than guessed at. Without `force` the backend returns the
   * stored analysis untouched, which is what makes a revisit free.
   */
  runAnalysis: async (type, force = false) => {
    const chat = get().activeChat
    if (!chat || get().isAnalyzing) return

    set({ isAnalyzing: true, analysisError: null, analysisErrorStatus: null })
    try {
      const analysis = await runAnalysisRequest(chat.id, type, force)
      const messages = await listMessages(chat.id)

      set((state) => ({
        analysis,
        messages: fromServer(messages),
        isAnalyzing: false,
        activeChat: state.activeChat
          ? {
              ...state.activeChat,
              analysis_type: analysis.type,
              has_analysis: true,
            }
          : state.activeChat,
      }))

      useChatListStore.getState().updateChat(chat.id, {
        analysis_type: analysis.type,
        has_analysis: true,
      })
      useTrackerStore
        .getState()
        .updateEntry(chat.id, { analysis_type: analysis.type })
    } catch (error) {
      set({
        isAnalyzing: false,
        analysisErrorStatus: apiErrorStatus(error) ?? null,
        analysisError: apiErrorMessage(
          error,
          'The analysis could not be completed. Please try again.',
        ),
      })
    }
  },

  appendUserMessage: (content) => {
    const chatId = get().activeChat?.id ?? ''
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: localId('local-user'),
          chat_id: chatId,
          role: 'user',
          content,
          kind: 'chat',
          created_at: new Date().toISOString(),
        },
      ],
    }))
  },

  /**
   * Opens the assistant bubble the tokens will flow into. It starts empty and
   * pending, which is what the thread renders as the typing indicator, so the
   * bubble does not jump position when the first token lands.
   */
  startAssistantMessage: (messageId, kind) => {
    const chatId = get().activeChat?.id ?? ''
    set((state) => ({
      streamingMessageId: messageId,
      messages: [
        ...state.messages,
        {
          id: messageId,
          chat_id: chatId,
          role: 'assistant',
          content: '',
          kind,
          created_at: new Date().toISOString(),
          pending: true,
        },
      ],
    }))
  },

  appendToken: (token) => {
    const streamingMessageId = get().streamingMessageId
    if (!streamingMessageId) return
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === streamingMessageId
          ? { ...message, content: message.content + token }
          : message,
      ),
    }))
  },

  /** Replaces the streamed text with the server's canonical copy. */
  finalizeAssistantMessage: (messageId, content) => {
    set((state) => ({
      streamingMessageId: null,
      isStreaming: false,
      messages: state.messages.map((message) =>
        message.id === messageId || message.id === state.streamingMessageId
          ? {
              ...message,
              id: messageId,
              content: content || message.content,
              pending: false,
              errored: false,
              errorMessage: undefined,
            }
          : message,
      ),
    }))
  },

  /**
   * Ends the stream in failure while keeping whatever text arrived. The bubble
   * stays on screen carrying the partial answer and an errored flag, which is
   * what puts the Retry action in front of the user.
   */
  markError: (message, partialContent, messageId) => {
    set((state) => {
      const streamingMessageId = state.streamingMessageId
      const target = state.messages.find((m) => m.id === streamingMessageId)

      // The request was rejected before a `start` event, so there is no bubble
      // to annotate: add one that carries only the failure.
      if (!target) {
        return {
          isStreaming: false,
          streamingMessageId: null,
          messages: [
            ...state.messages,
            {
              id: localId('local-error'),
              chat_id: state.activeChat?.id ?? '',
              role: 'assistant' as const,
              content: partialContent ?? '',
              kind: 'chat' as const,
              created_at: new Date().toISOString(),
              pending: false,
              errored: true,
              errorMessage: message,
            },
          ],
        }
      }

      return {
        isStreaming: false,
        streamingMessageId: null,
        messages: state.messages.map((m) =>
          m.id === streamingMessageId
            ? {
                ...m,
                // A persisted partial comes back under an id the server owns;
                // adopt it so the bubble on screen names the stored row.
                id: messageId ?? m.id,
                // The backend reports what it managed to persist; prefer it,
                // but never discard tokens already on screen for an empty one.
                content: partialContent || m.content,
                pending: false,
                errored: true,
                errorMessage: message,
              }
            : m,
        ),
      }
    })
  },

  sendMessage: async (content) => {
    const text = content.trim()
    const chat = get().activeChat
    if (!text || !chat || get().isStreaming) return

    get().appendUserMessage(text)
    await runStream(chat.id, text, set, get)
  },

  /**
   * Retries the last turn after a failure or a stop.
   *
   * The user's message is already in the thread, so only the failed assistant
   * bubble is dropped before re-posting. Note the backend stores a user row
   * before it starts streaming: a retry after a mid-stream failure therefore
   * leaves two copies of the turn on the server, and a later reload shows the
   * abandoned attempt. That is the honest record of what happened, and there is
   * no regenerate endpoint that would avoid it.
   */
  retryLast: async () => {
    const chat = get().activeChat
    if (!chat || get().isStreaming) return

    const messages = get().messages
    // Hand-rolled reverse scans: the lib target is ES2020, which predates
    // Array.prototype.findLast / findLastIndex.
    let failedIndex = -1
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].errored) {
        failedIndex = i
        break
      }
    }
    if (failedIndex === -1) return

    let lastUser: ThreadMessage | undefined
    for (let i = failedIndex - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'user') {
        lastUser = messages[i]
        break
      }
    }
    if (!lastUser) return

    set({ messages: messages.filter((_, i) => i !== failedIndex) })
    await runStream(chat.id, lastUser.content, set, get)
  },

  abortStream: () => {
    controller?.abort()
    controller = null
  },

  reset: () => {
    controller?.abort()
    controller = null
    loadToken += 1
    set({ ...emptyChat })
  },
}))

type SetState = (
  partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>),
) => void
type GetState = () => ChatState

/**
 * Drives one streamed reply from POST to the last frame.
 *
 * Shared by `sendMessage` and `retryLast` so the two differ only in whether
 * the user's bubble is appended first.
 */
async function runStream(
  chatId: string,
  content: string,
  set: SetState,
  get: GetState,
): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal

  set({ isStreaming: true, streamingMessageId: null, error: null })

  // Every handler is gated on the chat still being the one on screen. Aborting
  // a stream to open another chat resolves a beat later, and its final frame
  // must not append a bubble to the thread that replaced it.
  const stillHere = () => get().activeChat?.id === chatId

  await streamMessage(
    chatId,
    content,
    {
      onStart: (event) => {
        if (stillHere()) get().startAssistantMessage(event.message_id, event.kind)
      },
      onToken: (token) => {
        if (stillHere()) get().appendToken(token)
      },
      onDone: (event) => {
        if (stillHere()) {
          get().finalizeAssistantMessage(event.message_id, event.content)
        }
      },
      onError: (event) => {
        if (stillHere()) {
          get().markError(
            event.message,
            event.content,
            // Only a persisted partial has a row behind its id.
            event.partial ? event.message_id : undefined,
          )
        }
      },
    },
    signal,
  )

  // A newer stream may already own the controller; only clear our own.
  if (controller?.signal === signal) controller = null

  // The stream ended without a done or an error frame — the connection closed
  // clean but early. Leaving the bubble pending would spin forever, so end it
  // the same way a failure does: partial text, and a retry.
  if (stillHere() && get().isStreaming) {
    get().markError('The reply ended before it finished.')
  }
}

export default useChatStore
