import { useCallback } from 'react'
import { useChatStore } from '../store/chatStore'

export interface UseStreamResult {
  /** Posts a user turn and streams the reply into the active chat. */
  send: (content: string) => Promise<void>
  /** Re-sends the last turn after a failed or stopped stream. */
  retry: () => Promise<void>
  /** Cancels the stream in flight, keeping whatever text arrived. */
  abort: () => void
  isStreaming: boolean
  /**
   * Posted, but the server has not named the reply yet — the window where the
   * thread shows a typing indicator with no bubble behind it.
   */
  isConnecting: boolean
  /** True from the `start` frame until the first token lands. */
  isAwaitingFirstToken: boolean
  /** The partial text currently being streamed, or ''. */
  streamingContent: string
}

/**
 * The chat page's handle on the SSE stream.
 *
 * The transport lives in `services/messages.streamMessage` and the state
 * transitions live in `chatStore` — token appends, the final replace, and the
 * errored-with-partial-text state that puts a Retry in front of the user. This
 * hook is the thin component-facing surface over the two, so a component never
 * touches an AbortController or an SSE frame.
 */
export function useStream(): UseStreamResult {
  const sendMessage = useChatStore((state) => state.sendMessage)
  const retryLast = useChatStore((state) => state.retryLast)
  const abortStream = useChatStore((state) => state.abortStream)
  const isStreaming = useChatStore((state) => state.isStreaming)
  const streamingMessageId = useChatStore((state) => state.streamingMessageId)
  const streamingContent = useChatStore(
    (state) =>
      state.messages.find((message) => message.id === state.streamingMessageId)
        ?.content ?? '',
  )

  const send = useCallback(
    (content: string) => sendMessage(content),
    [sendMessage],
  )
  const retry = useCallback(() => retryLast(), [retryLast])
  const abort = useCallback(() => abortStream(), [abortStream])

  return {
    send,
    retry,
    abort,
    isStreaming,
    isConnecting: isStreaming && !streamingMessageId,
    // Between POST and the `start` frame there is no message id yet; between
    // `start` and the first token the bubble exists but is still empty.
    isAwaitingFirstToken:
      isStreaming && (!streamingMessageId || streamingContent.length === 0),
    streamingContent,
  }
}

export default useStream
