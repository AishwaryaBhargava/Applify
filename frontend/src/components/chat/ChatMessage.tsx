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
  Printer,
  RotateCcw,
  type LucideIcon,
} from 'lucide-react'
import TypingIndicator from './TypingIndicator'
import Spinner from '../common/Spinner'
import { downloadOutputFile, printOutputPath } from './exportActions'
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
  /** Needed to address the export endpoint; omitted on the welcome thread. */
  chatId?: string
  /**
   * The `generated_outputs` row this bubble was filed under, resolved by the
   * thread. Null while a document is still streaming — it is not filed until
   * the last token lands — which is exactly when the file actions must not be
   * offered.
   */
  outputId?: string | null
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
  chatId,
  outputId,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const [exporting, setExporting] = useState(false)
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

  const fileBase = `${slugify(documentName?.trim() || 'applify')}-${chip?.fileSuffix ?? 'document'}`

  const download = useCallback(() => {
    if (!chip?.fileSuffix) return
    const base = slugify(documentName?.trim() || 'applify')
    downloadTextFile(`${base}-${chip.fileSuffix}.md`, message.content)
  }, [chip, documentName, message.content])

  /**
   * The .docx is built server-side, so unlike the markdown download it is a
   * request that can fail and has to be waited for.
   */
  const downloadDocx = useCallback(async () => {
    if (!chatId || !outputId || exporting) return
    setExporting(true)
    await downloadOutputFile(chatId, outputId, 'docx', `${fileBase}.docx`)
    setExporting(false)
  }, [chatId, exporting, fileBase, outputId])

  // One class for every action under a bubble: they are a row of equals, and
  // they fade in together on hover once there is a mouse to hover with.
  const actionClass =
    'flex min-h-[40px] items-center gap-1 text-[12px] text-text-faint transition-opacity hover:text-text-secondary focus:opacity-100 disabled:opacity-50 sm:min-h-0 sm:text-[11px] sm:opacity-0 sm:group-hover:opacity-100'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] overflow-hidden whitespace-pre-wrap break-words rounded-box rounded-br-[2px] bg-teal-deep px-3.5 py-2.5 text-[13px] leading-relaxed text-white sm:max-w-[80%]">
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

      <div className="max-w-full overflow-hidden break-words rounded-box rounded-bl-[2px] bg-surface-warm px-3.5 py-2.5 text-[13px] leading-relaxed text-text-primary sm:max-w-[85%]">
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
            className={actionClass}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>

          {isDocument && (
            <button
              type="button"
              onClick={download}
              aria-label="Download as markdown"
              className={actionClass}
            >
              <Download size={12} />
              Download .md
            </button>
          )}

          {/* Both server-side actions need the stored output row behind the
              bubble; a document that never finished streaming has none. */}
          {isDocument && chatId && outputId && (
            <>
              <button
                type="button"
                onClick={() => void downloadDocx()}
                disabled={exporting}
                aria-label="Download as Word document"
                className={actionClass}
              >
                {exporting ? <Spinner size={12} /> : <Download size={12} />}
                Download .docx
              </button>

              {/*
                A link rather than a button: opening the print view in a new tab
                keeps the conversation exactly where it was, and a real anchor
                is what lets the user middle-click or copy the address.
              */}
              <a
                href={printOutputPath(chatId, outputId)}
                target="_blank"
                rel="noopener noreferrer"
                className={actionClass}
              >
                <Printer size={12} />
                Print / Save as PDF
              </a>
            </>
          )}
        </div>
      )}
    </div>
  )
}
