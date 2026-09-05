import { useCallback, useState, type FormEvent } from 'react'
import { FileText, Mail, MessageSquare, X, type LucideIcon } from 'lucide-react'
import type { OutputType } from '../../types'

interface OutputActionsProps {
  /** Streams the document; the answer form sends the question as context. */
  onGenerate: (outputType: OutputType, userContext?: string) => void
  disabled?: boolean
}

interface Chip {
  type: OutputType
  label: string
  icon: LucideIcon
  className: string
}

/**
 * The three things worth asking for once a fit analysis exists. Coloured by
 * document, matching the header chip each one will stream in under.
 */
const CHIPS: Chip[] = [
  {
    type: 'resume',
    label: 'Tailor my resume',
    icon: FileText,
    className: 'bg-teal-light text-teal-ink hover:bg-teal-soft/50',
  },
  {
    type: 'cover_letter',
    label: 'Write a cover letter',
    icon: Mail,
    className: 'bg-coral-light text-coral-ink hover:bg-coral-light/70',
  },
  {
    type: 'answer',
    label: 'Help with a question',
    icon: MessageSquare,
    className: 'bg-amber-light text-amber-ink hover:bg-amber-light/70',
  },
]

/**
 * Quick actions above the composer.
 *
 * A shortcut, never the only way in: asking for any of these in plain words
 * streams the identical document under the identical `kind`, because the
 * backend's intent router and this button reach the same generator. The
 * question form exists because an application question is usually pasted, and
 * pasting a wall of text into a chat box to have it answered reads worse than
 * a field that says what it wants.
 */
export default function OutputActions({
  onGenerate,
  disabled = false,
}: OutputActionsProps) {
  const [askOpen, setAskOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [emphasis, setEmphasis] = useState('')

  const submitQuestion = useCallback(
    (event: FormEvent) => {
      event.preventDefault()
      const text = question.trim()
      if (!text || disabled) return

      const extra = emphasis.trim()
      onGenerate('answer', extra ? `${text}\n\nPlease emphasise: ${extra}` : text)

      setQuestion('')
      setEmphasis('')
      setAskOpen(false)
    },
    [disabled, emphasis, onGenerate, question],
  )

  return (
    <div className="border-t border-border bg-bg px-4 pt-3 md:px-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium tracking-[0.8px] text-text-muted">
            GENERATE
          </span>
          {CHIPS.map(({ type, label, icon: Icon, className }) => (
            <button
              key={type}
              type="button"
              disabled={disabled}
              onClick={() =>
                type === 'answer'
                  ? setAskOpen((open) => !open)
                  : onGenerate(type)
              }
              aria-expanded={type === 'answer' ? askOpen : undefined}
              className={`flex items-center gap-1.5 rounded-pill px-2.5 py-[5px] text-[12px] font-medium transition-colors disabled:opacity-50 ${className}`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {askOpen && (
          <form
            onSubmit={submitQuestion}
            className="mt-2.5 rounded-box border border-border bg-card p-3"
          >
            <div className="mb-2 flex items-center justify-between">
              <label
                htmlFor="application-question"
                className="text-[11px] font-medium tracking-[0.8px] text-text-muted"
              >
                APPLICATION QUESTION
              </label>
              <button
                type="button"
                onClick={() => setAskOpen(false)}
                aria-label="Close question form"
                className="text-text-faint hover:text-text-secondary"
              >
                <X size={14} />
              </button>
            </div>

            <textarea
              id="application-question"
              rows={3}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Paste the application question"
              className="w-full resize-y rounded-input border border-border-input bg-card px-3 py-2 text-[13px] leading-relaxed outline-none focus:border-teal-deep"
            />

            <input
              type="text"
              value={emphasis}
              onChange={(event) => setEmphasis(event.target.value)}
              placeholder="Anything to emphasise? (optional)"
              className="mt-2 w-full rounded-input border border-border-input bg-card px-3 py-2 text-[13px] outline-none focus:border-teal-deep"
            />

            <div className="mt-2.5 flex justify-end">
              <button
                type="submit"
                disabled={disabled || !question.trim()}
                className="rounded-btn bg-coral px-3.5 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Draft an answer
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
