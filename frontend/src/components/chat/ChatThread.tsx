import ChatMessage from './ChatMessage'
import useAutoScroll from '../../hooks/useAutoScroll'
import type { ChatMessage as ChatMessageType } from '../../types'

interface ChatThreadProps {
  messages?: ChatMessageType[]
}

/**
 * Scrollable message thread.
 * TODO(Phase 6): render streaming tokens as a live assistant bubble.
 */
export default function ChatThread({ messages = [] }: ChatThreadProps) {
  const scrollRef = useAutoScroll<HTMLDivElement>([messages.length])

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5">
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
      </div>
    </div>
  )
}
