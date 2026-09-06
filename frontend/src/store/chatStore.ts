import { create } from 'zustand'
import { apiErrorMessage, apiErrorStatus } from '../services/api'
import {
  runAnalysis as runAnalysisRequest,
  runKeywordMatch as runKeywordMatchRequest,
} from '../services/analysis'
import { getChat } from '../services/chats'
import { listMessages, streamMessage } from '../services/messages'
import { listOutputs, streamOutput } from '../services/outputs'
import { useChatListStore } from './chatListStore'
import { pushToast } from './toastStore'
import { useTrackerStore } from './trackerStore'
import type {
  Analysis,
  AnalysisType,
  ChatMessage,
  GeneratedOutput,
  JobChat,
  KeywordMatch,
  MessageKind,
  OutputType,
  StreamDoneEvent,
  StreamErrorEvent,
  StreamStartEvent,
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

/**
 * The user turn each output button stands for. Mirrors `BUTTON_MESSAGES` in
 * backend/app/api/routes/outputs.py: the server persists exactly this text, so
 * the optimistic bubble and the stored row have to read the same or a reload
 * would silently rewrite what the user "said".
 */
const BUTTON_MESSAGES: Record<OutputType, string> = {
  resume: 'Generate a tailored resume for this role',
  cover_letter: 'Write a cover letter for this role',
  answer: 'Answer this application question',
}

/** The message kinds that are generated documents rather than a chat turn. */
const OUTPUT_KINDS: OutputType[] = ['resume', 'cover_letter', 'answer']

function isOutputKind(kind: MessageKind): kind is OutputType {
  return (OUTPUT_KINDS as MessageKind[]).includes(kind)
}

/** Composes the user message an output button stands for. */
export function buttonMessage(
  outputType: OutputType,
  userContext?: string | null,
): string {
  const context = (userContext ?? '').trim()
  const base = BUTTON_MESSAGES[outputType]
  return context ? `${base}: ${context}` : base
}

/**
 * One streamed turn, described well enough to be replayed on a retry: the
 * message path posts to `/messages`, the button path to `/outputs`, and only
 * the request itself knows which of the two produced the bubble on screen.
 */
type StreamRequest =
  | { mode: 'message'; content: string }
  | {
      mode: 'output'
      outputType: OutputType
      userContext?: string
      content: string
    }

/**
 * The request behind the turn now on screen, so `retryLast` re-posts to the
 * endpoint that produced it. Module scope for the same reason as the abort
 * controller: nothing renders from it.
 */
let lastRequest: StreamRequest | null = null

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
  /** The stored ATS keyword match, or null until one has been run here. */
  keywordMatch: KeywordMatch | null

  isLoadingChat: boolean
  isAnalyzing: boolean
  isMatchingKeywords: boolean
  isStreaming: boolean
  /** Id of the assistant message currently being streamed into. */
  streamingMessageId: string | null

  /** Load / delete failures for the chat as a whole. */
  error: string | null
  /** Failures of the last analyze request, shown inside the analysis area. */
  analysisError: string | null
  /** HTTP status of that failure. 409 means "upload your resume first". */
  analysisErrorStatus: number | null
  /** Failures of the last keyword request, shown inside the keyword panel. */
  keywordError: string | null
  /** Its HTTP status. 409 is the same "upload your resume first" as above. */
  keywordErrorStatus: number | null

  setActiveChat: (chat: JobChat | null) => void
  setMessages: (messages: ThreadMessage[]) => void
  setAnalysis: (analysis: Analysis | null) => void
  setOutputs: (outputs: GeneratedOutput[]) => void
  /** Inserts newest-first, replacing any earlier copy of the same output. */
  addOutput: (output: GeneratedOutput) => void
  /** Files a finished document and flips the tracker when it was a resume. */
  recordOutput: (kind: OutputType, event: StreamDoneEvent) => void

  setKeywordMatch: (match: KeywordMatch | null) => void

  loadChat: (chatId: string) => Promise<void>
  fetchOutputs: (chatId?: string) => Promise<void>
  runAnalysis: (type: AnalysisType, force?: boolean) => Promise<void>
  /**
   * Runs the ATS keyword match. Without `force` the stored keyword list is
   * reused and only the matching re-runs, which is what makes "I just added
   * that skill, check again" cheap.
   */
  runKeywordMatch: (force?: boolean) => Promise<void>

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
  /** Asks for a document explicitly, through POST /chats/{id}/outputs. */
  generateOutput: (
    outputType: OutputType,
    userContext?: string,
  ) => Promise<void>
  /** Re-sends the last user turn after a failed or stopped stream. */
  retryLast: () => Promise<void>
  abortStream: () => void

  clearError: () => void
  clearAnalysisError: () => void
  clearKeywordError: () => void
  reset: () => void
}

const emptyChat = {
  activeChat: null,
  messages: [] as ThreadMessage[],
  analysis: null,
  outputs: [] as GeneratedOutput[],
  keywordMatch: null,
  isLoadingChat: false,
  isAnalyzing: false,
  isMatchingKeywords: false,
  isStreaming: false,
  streamingMessageId: null,
  error: null,
  analysisError: null,
  analysisErrorStatus: null,
  keywordError: null,
  keywordErrorStatus: null,
}

export const useChatStore = create<ChatState>((set, get) => ({
  ...emptyChat,

  setActiveChat: (activeChat) => set({ activeChat }),
  setMessages: (messages) => set({ messages }),
  setAnalysis: (analysis) => set({ analysis }),
  setKeywordMatch: (keywordMatch) => set({ keywordMatch }),
  setOutputs: (outputs) => set({ outputs }),
  addOutput: (output) =>
    set((state) => ({
      outputs: [
        output,
        ...state.outputs.filter((row) => row.id !== output.id),
      ],
    })),

  /**
   * What a finished document changes beyond the bubble it streamed into.
   *
   * The `done` frame carries the id the output was filed under and, for a
   * resume, the tracker's new `resume_type` — so the outputs list, the sidebar
   * row and the tracker table are all correct the moment the last token lands,
   * with no refetch. A resume asked for in plain words arrives through exactly
   * the same frames, so both paths land here.
   */
  recordOutput: (kind, event) => {
    const chat = get().activeChat
    if (!chat) return

    if (event.output_id) {
      get().addOutput({
        id: event.output_id,
        chat_id: chat.id,
        output_type: kind,
        content: event.content,
        created_at: new Date().toISOString(),
      })
    }

    if (kind !== 'resume') return

    const resumeType = event.resume_type ?? 'tailored'
    set((state) => ({
      activeChat: state.activeChat
        ? { ...state.activeChat, resume_type: resumeType }
        : state.activeChat,
    }))
    useChatListStore.getState().updateChat(chat.id, { resume_type: resumeType })
    useTrackerStore
      .getState()
      .updateEntry(chat.id, { resume_type: resumeType })
    pushToast('Tracker updated: AI-tailored resume', 'success')
  },

  clearError: () => set({ error: null }),
  clearAnalysisError: () => set({ analysisError: null, analysisErrorStatus: null }),
  clearKeywordError: () =>
    set({ keywordError: null, keywordErrorStatus: null }),

  /**
   * Rebuilds the page from `GET /chats/{id}`: chat, full history, and the
   * stored analysis. Any stream still running for the previous chat is aborted
   * first so its tokens cannot land in the new thread.
   */
  loadChat: async (chatId) => {
    get().abortStream()
    lastRequest = null
    const token = ++loadToken
    const switching = get().activeChat?.id !== chatId

    set({
      isLoadingChat: true,
      error: null,
      analysisError: null,
      analysisErrorStatus: null,
      keywordError: null,
      keywordErrorStatus: null,
      // Keep the current thread visible when reloading the same chat; clear it
      // when moving to a different one so the old messages never flash.
      ...(switching
        ? {
            messages: [],
            analysis: null,
            activeChat: null,
            outputs: [],
            keywordMatch: null,
          }
        : {}),
    })

    try {
      const detail = await getChat(chatId)
      if (token !== loadToken) return

      const { messages, analysis, keyword_match: keywordMatch, ...chat } = detail
      set({
        activeChat: chat,
        messages: fromServer(messages),
        analysis,
        // A backend from before the keyword phase omits the key; `?? null`
        // renders that as "not run yet" rather than as undefined.
        keywordMatch: keywordMatch ?? null,
        isLoadingChat: false,
      })
      // The sidebar row may predate the analysis; keep the two in step.
      useChatListStore.getState().updateChat(chatId, chat)
      // The documents already generated here, for the outputs list. Not
      // awaited: the thread is readable without it.
      void get().fetchOutputs(chatId)
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
   * GET /chats/{id}/outputs — the documents generated in this chat.
   *
   * Failure is swallowed on purpose: this is a history list beside the thread,
   * and the documents themselves are already in the messages. An empty section
   * is a better answer than an error banner over a chat that works.
   */
  fetchOutputs: async (chatId) => {
    const id = chatId ?? get().activeChat?.id
    if (!id) return
    try {
      const outputs = await listOutputs(id)
      if (get().activeChat?.id === id) set({ outputs })
    } catch {
      // Older backend (501 before Phase 7) or a transport failure.
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
      const status = apiErrorStatus(error) ?? null
      const message = apiErrorMessage(
        error,
        'The analysis could not be completed. Please try again.',
      )
      set({
        isAnalyzing: false,
        analysisErrorStatus: status,
        analysisError: message,
      })
      // The inline block under the picker explains what to do; the toast is
      // what makes the failure impossible to miss when the picker has been
      // scrolled past. A missing profile is a precondition rather than a
      // fault, so it gets the short version.
      pushToast(
        status === NO_PROFILE_STATUS
          ? 'Upload your resume to run an analysis'
          : message,
        'error',
      )
    }
  },

  /**
   * Runs the ATS keyword match and keeps the result on the page.
   *
   * Unlike the analysis this does **not** refetch the thread: the match is a
   * panel beside the chat, not a message in it, so nothing in the conversation
   * changes. A failure is left in `keywordError` for the panel to render
   * inline — including the 409 that means there is no profile to match
   * against, which the panel answers with the same resume nudge the analysis
   * picker uses.
   */
  runKeywordMatch: async (force = false) => {
    const chat = get().activeChat
    if (!chat || get().isMatchingKeywords) return

    set({
      isMatchingKeywords: true,
      keywordError: null,
      keywordErrorStatus: null,
    })
    try {
      const keywordMatch = await runKeywordMatchRequest(chat.id, force)
      // The user may have opened another chat while this ran; its keywords are
      // not this chat's.
      if (get().activeChat?.id !== chat.id) return
      set({ keywordMatch, isMatchingKeywords: false })
    } catch (error) {
      if (get().activeChat?.id !== chat.id) return
      const status = apiErrorStatus(error) ?? null
      const message = apiErrorMessage(
        error,
        'The keyword match could not be completed. Please try again.',
      )
      set({
        isMatchingKeywords: false,
        keywordErrorStatus: status,
        keywordError: message,
      })
      // The panel explains a missing profile in its own words; a toast saying
      // it again would be the second copy of a message the user is looking at.
      if (status !== NO_PROFILE_STATUS) pushToast(message, 'error')
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
    await runStream(chat.id, { mode: 'message', content: text }, set, get)
  },

  /**
   * The quick-action path: asks for a document by name rather than by phrasing
   * it in chat. The backend persists the same user turn either way, so the
   * thread reads identically whichever route the user took.
   */
  generateOutput: async (outputType, userContext) => {
    const chat = get().activeChat
    if (!chat || get().isStreaming) return

    const content = buttonMessage(outputType, userContext)
    get().appendUserMessage(content)
    await runStream(
      chat.id,
      { mode: 'output', outputType, userContext, content },
      set,
      get,
    )
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
    // A document asked for through a button has to be retried against
    // /outputs: re-posting its user turn to /messages would leave the document
    // type to intent detection, which is not what the user clicked.
    const request: StreamRequest =
      lastRequest && lastRequest.content === lastUser.content
        ? lastRequest
        : { mode: 'message', content: lastUser.content }
    await runStream(chat.id, request, set, get)
  },

  abortStream: () => {
    controller?.abort()
    controller = null
  },

  reset: () => {
    controller?.abort()
    controller = null
    lastRequest = null
    loadToken += 1
    set({ ...emptyChat })
  },
}))

type SetState = (
  partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>),
) => void
type GetState = () => ChatState

/**
 * Drives one streamed turn from POST to the last frame.
 *
 * Shared by `sendMessage`, `generateOutput` and `retryLast`. The two endpoints
 * emit byte-identical frames — the backend reuses one generator for both — so
 * only the first line here differs between them, and everything downstream,
 * including a document that arrived because the user simply asked for one in
 * words, is handled in exactly one place.
 */
async function runStream(
  chatId: string,
  request: StreamRequest,
  set: SetState,
  get: GetState,
): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  lastRequest = request

  set({ isStreaming: true, streamingMessageId: null, error: null })

  // Every handler is gated on the chat still being the one on screen. Aborting
  // a stream to open another chat resolves a beat later, and its final frame
  // must not append a bubble to the thread that replaced it.
  const stillHere = () => get().activeChat?.id === chatId

  // The kind the server announced, so `done` knows whether this turn was a
  // document. It is authoritative over what was asked for: the intent router
  // may answer a "write me a cover letter" message with kind cover_letter.
  let kind: MessageKind = 'chat'

  const handlers = {
    onStart: (event: StreamStartEvent) => {
      if (!stillHere()) return
      kind = event.kind
      get().startAssistantMessage(event.message_id, event.kind)
    },
    onToken: (token: string) => {
      if (stillHere()) get().appendToken(token)
    },
    onDone: (event: StreamDoneEvent) => {
      if (!stillHere()) return
      get().finalizeAssistantMessage(event.message_id, event.content)
      if (isOutputKind(kind)) get().recordOutput(kind, event)
    },
    onError: (event: StreamErrorEvent) => {
      if (!stillHere()) return
      get().markError(
        event.message,
        event.content,
        // Only a persisted partial has a row behind its id.
        event.partial ? event.message_id : undefined,
      )
      // Stopping is something the user did, not something that went wrong.
      if (!signal.aborted) pushToast(event.message, 'error')
    },
  }

  if (request.mode === 'output') {
    await streamOutput(
      chatId,
      {
        output_type: request.outputType,
        ...(request.userContext?.trim()
          ? { user_context: request.userContext.trim() }
          : {}),
      },
      handlers,
      signal,
    )
  } else {
    await streamMessage(chatId, request.content, handlers, signal)
  }

  // A newer stream may already own the controller; only clear our own.
  if (controller?.signal === signal) controller = null

  // The stream ended without a done or an error frame — the connection closed
  // clean but early. Leaving the bubble pending would spin forever, so end it
  // the same way a failure does: partial text, and a retry.
  if (stillHere() && get().isStreaming) {
    const message = 'The reply ended before it finished.'
    get().markError(message)
    if (!signal.aborted) pushToast(message, 'error')
  }
}

export default useChatStore
