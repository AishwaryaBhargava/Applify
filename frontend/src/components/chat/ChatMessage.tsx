import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AlertCircle, Check, Copy, RotateCcw } from 'lucide-react'
import TypingIndicator from './TypingIndicator'
import Badge, { type BadgeTone } from '../common/Badge'
import type { MessageKind, ThreadMessage } from '../../types'

interface ChatMessageProps {
  message: ThreadMessage
  /** Offered on the errored bubble, which is always the last one. */
  onRetry?: () => void
}

/**
 * Header chips for messages that are not an ordinary turn, so a generated
 * document is recognisable at a glance in a long thread. `chat` gets none.
 */
const KIND_LABELS: Partial<Record<MessageKind, { label: string; tone: BadgeTone }>> =
  {
    analysis: { label: 'Fit analysis', tone: 'amber' },
    resume: { label: 'Tailored resume', tone: 'teal' },
    cover_letter: { label: 'Cover letter', tone: 'coral' },
    answer: { label: 'Application answer', tone: 'neutral' },
  }

/** One message bubble: user on the right, assistant on the left. */
export default function ChatMessage({ message, onRetry }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (copyTimer.current) clearTimeout(copyTimer.current)
    },
    [],
  )

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      copyTimer.current = setTimeout(() => setCopied(false), 1600)
    } catch {
      // Clipboard blocked (insecure origin, denied permission): the text is
      // still selectable, so say nothing rather than throwing an error at the
      // user for a convenience action.
    }
  }, [message.content])

  const isUser = message.role === 'user'
  const chip = isUser ? undefined : KIND_LABELS[message.kind]
  const isTyping = Boolean(message.pending) && message.content.length === 0

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-box rounded-br-[2px] bg-teal-deep px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="group flex flex-col items-start gap-1">
      {chip && <Badge tone={chip.tone}>{chip.label}</Badge>}

      <div className="max-w-[85%] rounded-box rounded-bl-[2px] bg-surface-warm px-3.5 py-2.5 text-[13px] leading-relaxed text-text-primary">
        {isTyping ? (
          <TypingIndicator />
        ) : (
          <div className="md-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {message.pending && (
              // A caret that blinks only while tokens are still arriving.
              <span
                aria-hidden="true"
                className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-teal-deep align-baseline"
              />
            )}
          </div>
        )}
      </div>

      {message.errored && (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-coral-ink">
          <span className="flex items-center gap-1.5">
            <AlertCircle size={13} />
            {message.errorMessage ?? 'That reply did not finish.'}
          </span>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="flex items-center gap-1 rounded-pill bg-coral-light px-2 py-[3px] font-medium text-coral-ink hover:opacity-80"
            >
              <RotateCcw size={12} />
              Retry
            </button>
          )}
        </div>
      )}

      {!message.pending && message.content.length > 0 && (
        <button
          type="button"
          onClick={copy}
          aria-label="Copy message"
          className="flex items-center gap-1 text-[11px] text-text-faint opacity-0 transition-opacity hover:text-text-secondary focus:opacity-100 group-hover:opacity-100"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      )}
    </div>
  )
}
