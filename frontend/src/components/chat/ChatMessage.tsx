import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  AlertCircle,
  Check,
  ClipboardCheck,
  Copy,
  Download,
  FileText,
  Mail,
  MessageSquare,
  RotateCcw,
  type LucideIcon,
} from 'lucide-react'
import TypingIndicator from './TypingIndicator'
import { downloadTextFile } from '../../lib/download'
import { slugify } from '../../lib/format'
import type { MessageKind, ThreadMessage } from '../../types'

interface ChatMessageProps {
  message: ThreadMessage
  /** Offered on the errored bubble, which is always the last one. */
  onRetry?: () => void
  /**
   * What a downloaded document is named after — the company, falling back to
   * the role. "Kestrel Labs" becomes `Kestrel-Labs-resume.md`.
   */
  documentName?: string
}

interface KindChip {
  label: string
  icon: LucideIcon
  /** Light background plus its ink colour, per the brand palette. */
  className: string
  /** Documents get a Download button; an analysis is not one. */
  fileSuffix?: string
}

/**
 * Header chips for messages that are not an ordinary turn, so a generated
 * document is recognisable at a glance in a long thread. `chat` gets none.
 */
const KIND_CHIPS: Partial<Record<MessageKind, KindChip>> = {
  analysis: {
    label: 'Fit analysis',
    icon: ClipboardCheck,
    className: 'bg-amber-light text-amber-ink',
  },
  resume: {
    label: 'Tailored resume',
    icon: FileText,
    className: 'bg-teal-light text-teal-ink',
    fileSuffix: 'resume',
  },
  cover_letter: {
    label: 'Cover letter',
    icon: Mail,
    className: 'bg-coral-light text-coral-ink',
    fileSuffix: 'cover-letter',
  },
  answer: {
    label: 'Application answer',
    icon: MessageSquare,
    className: 'bg-amber-light text-amber-ink',
  },
}

/** One message bubble: user on the right, assistant on the left. */
export default function ChatMessage({
  message,
  onRetry,
  documentName,
}: ChatMessageProps) {
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
      // The raw markdown, not the rendered text: what the user pastes into a
      // document should be the document, headings and bullets intact.
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
  const chip = isUser ? undefined : KIND_CHIPS[message.kind]
  const isTyping = Boolean(message.pending) && message.content.length === 0
  const isDocument = Boolean(chip?.fileSuffix) && !message.pending

  const download = useCallback(() => {
    if (!chip?.fileSuffix) return
    const base = slugify(documentName?.trim() || 'applify')
    downloadTextFile(`${base}-${chip.fileSuffix}.md`, message.content)
  }, [chip, documentName, message.content])

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-box rounded-br-[2px] bg-teal-deep px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    )
  }

  const Icon = chip?.icon

  return (
    <div className="group flex flex-col items-start gap-1">
      {chip && Icon && (
        <span
          className={`inline-flex items-center gap-1.5 rounded-pill px-2 py-[3px] text-[11px] font-medium ${chip.className}`}
        >
          <Icon size={12} />
          {chip.label}
        </span>
      )}

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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={copy}
            aria-label="Copy message"
            className="flex items-center gap-1 text-[11px] text-text-faint opacity-0 transition-opacity hover:text-text-secondary focus:opacity-100 group-hover:opacity-100"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>

          {isDocument && (
            <button
              type="button"
              onClick={download}
              aria-label="Download as markdown"
              className="flex items-center gap-1 text-[11px] text-text-faint opacity-0 transition-opacity hover:text-text-secondary focus:opacity-100 group-hover:opacity-100"
            >
              <Download size={12} />
              Download .md
            </button>
          )}
        </div>
      )}
    </div>
  )
}
