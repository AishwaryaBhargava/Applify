import { useEffect, useRef, useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import Spinner from '../common/Spinner'

/** Short enough to be a paste slip, long enough to be a real posting. */
export const MIN_JD_LENGTH = 50

interface NewChatModalProps {
  open: boolean
  onClose: () => void
  /** Resolves to true when the chat was created and the modal may close. */
  onCreate: (title: string, company: string, jdText: string) => Promise<boolean>
  /** Failure from the create request, shown under the form. */
  error?: string | null
}

/**
 * The new-chat form: job title, company, and the job description.
 *
 * The JD is required because everything downstream is grounded in it — an
 * analysis without one is just the model guessing.
 */
export default function NewChatModal({
  open,
  onClose,
  onCreate,
  error,
}: NewChatModalProps) {
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [jdText, setJdText] = useState('')
  const [touched, setTouched] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const titleRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) return
    setTitle('')
    setCompany('')
    setJdText('')
    setTouched(false)
    setIsSubmitting(false)
    titleRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const trimmedJd = jdText.trim()
  const titleError = !title.trim() ? 'Add the job title.' : null
  const jdError = !trimmedJd
    ? 'Paste the job description.'
    : trimmedJd.length < MIN_JD_LENGTH
      ? `That looks short — paste at least ${MIN_JD_LENGTH} characters.`
      : null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (titleError || jdError || isSubmitting) return

    setIsSubmitting(true)
    const created = await onCreate(title, company, jdText)
    setIsSubmitting(false)
    if (created) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/20 p-0 sm:items-center sm:p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-chat-title"
        className="flex max-h-[92dvh] w-full max-w-xl flex-col overflow-hidden rounded-t-panel border border-border bg-card text-left sm:max-h-[90dvh] sm:rounded-panel"
      >
        <header className="flex flex-shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-6">
          <div>
            <h2
              id="new-chat-title"
              className="font-serif text-lg font-medium text-teal-ink"
            >
              New job chat
            </h2>
            <p className="mt-0.5 text-[12px] text-text-muted">
              One workspace per opening — analysis, chat, and outputs all live
              here.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 -mt-1.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-text-muted hover:bg-surface-warm hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </header>

        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-5 sm:px-6"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-medium text-text-secondary">
                Job title
              </span>
              <input
                ref={titleRef}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Senior Product Designer"
                className="min-h-[44px] rounded-input border border-border-input bg-card px-3 py-2 text-[16px] outline-none focus:border-teal-deep sm:min-h-0 sm:text-[13px]"
              />
              {touched && titleError && (
                <span className="text-[11px] text-coral-ink">{titleError}</span>
              )}
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-medium text-text-secondary">
                Company
              </span>
              <input
                value={company}
                onChange={(event) => setCompany(event.target.value)}
                placeholder="Stripe"
                className="min-h-[44px] rounded-input border border-border-input bg-card px-3 py-2 text-[16px] outline-none focus:border-teal-deep sm:min-h-0 sm:text-[13px]"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-text-secondary">
              Job description
            </span>
            <textarea
              value={jdText}
              onChange={(event) => setJdText(event.target.value)}
              rows={6}
              placeholder="Paste the full posting — responsibilities, requirements, everything."
              className="resize-y rounded-input border border-border-input bg-card px-3 py-2 text-[16px] leading-relaxed outline-none focus:border-teal-deep sm:text-[13px]"
            />
            <span className="flex items-center justify-between text-[11px]">
              <span className="text-coral-ink">
                {touched && jdError ? jdError : ''}
              </span>
              <span className="flex-shrink-0 text-[12px] text-text-faint sm:text-[11px]">
                {trimmedJd.length} characters
              </span>
            </span>
          </label>

          {error && (
            <p className="rounded-input bg-coral-light px-3 py-2 text-[12px] text-coral-ink">
              {error}
            </p>
          )}

          <div className="sticky bottom-0 -mx-5 flex justify-end gap-2 border-t border-border bg-card px-5 pb-1 pt-3 sm:-mx-6 sm:px-6">
            <button
              type="button"
              onClick={onClose}
              className="min-h-[42px] rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex min-h-[42px] items-center gap-2 rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {isSubmitting && <Spinner size={14} className="text-white" />}
              {isSubmitting ? 'Creating...' : 'Create chat'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
