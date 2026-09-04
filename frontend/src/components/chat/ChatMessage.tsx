import ReactMarkdown from 'react-markdown'
import type { ChatMessage as ChatMessageType } from '../../types'

interface ChatMessageProps {
  message: ChatMessageType
}

/**
 * Individual message bubble.
 * TODO(Phase 6): add copy action for generated outputs.
 */
export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[80%] px-3.5 py-2.5 text-[13px] leading-relaxed',
          isUser
            ? 'rounded-box rounded-br-[2px] bg-teal-light text-teal-ink'
            : 'rounded-box rounded-bl-[2px] bg-surface-warm text-text-primary',
        ].join(' ')}
      >
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  )
}
