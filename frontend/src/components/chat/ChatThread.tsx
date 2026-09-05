import type { ReactNode } from 'react'
import ChatMessage from './ChatMessage'
import TypingIndicator from './TypingIndicator'
import useAutoScroll from '../../hooks/useAutoScroll'
import type { ThreadMessage } from '../../types'

interface ChatThreadProps {
  messages: ThreadMessage[]
  onRetry?: () => void
  /** Rendered above the messages: the analysis card or the depth picker. */
  header?: ReactNode
  /**
   * True after the message is posted but before the server names the reply.
   * The backend does a little database work before its first frame, so without
   * this the send would land in silence.
   */
  isConnecting?: boolean
  /** Passed to each bubble: what a downloaded document is named after. */
  documentName?: string
}

/** Length of the newest message, so auto-scroll keeps up token by token. */
function newestLength(messages: ThreadMessage[]): number {
  const last = messages[messages.length - 1]
  return last ? last.content.length : 0
}

/**
 * The scrollable message thread.
 *
 * Auto-scroll follows the newest content while the user is at the bottom and
 * lets go the moment they scroll up to read something earlier — see
 * `useAutoScroll`. The streamed length is part of the dependency list so the
 * view keeps up token by token, not just message by message.
 */
export default function ChatThread({
  messages,
  onRetry,
  header,
  isConnecting = false,
  documentName,
}: ChatThreadProps) {
  const { ref } = useAutoScroll<HTMLDivElement>([
    messages.length,
    newestLength(messages),
    isConnecting,
    Boolean(header),
  ])

  // Only the last failed bubble gets the retry: retrying an older turn would
  // append its answer to the end of the thread, out of order.
  const lastErroredIndex = messages.reduce(
    (found, message, index) => (message.errored ? index : found),
    -1,
  )

  return (
    <div ref={ref} className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {header}

        {messages.map((message, index) => (
          <ChatMessage
            key={message.id}
            message={message}
            onRetry={index === lastErroredIndex ? onRetry : undefined}
            documentName={documentName}
          />
        ))}

        {isConnecting && (
          <div className="flex justify-start">
            <div className="rounded-box rounded-bl-[2px] bg-surface-warm px-3.5 py-2.5">
              <TypingIndicator />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
