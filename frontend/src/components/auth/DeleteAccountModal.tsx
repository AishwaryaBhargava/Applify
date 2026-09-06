import { useEffect, useId, useRef, useState } from 'react'
import Spinner from '../common/Spinner'

/** The word that has to be typed before the delete button does anything. */
export const DELETE_CONFIRMATION = 'DELETE'

interface DeleteAccountModalProps {
  open: boolean
  /** Disables both buttons and shows the spinner while the request is out. */
  isDeleting?: boolean
  /** A failure to report without closing the dialog. */
  error?: string | null
  onCancel: () => void
  onConfirm: () => void
}

/**
 * The account-deletion dialog.
 *
 * Its own component rather than a `ConfirmModal` with a prop: the point of this
 * dialog is the typed confirmation, and a shared confirm box that grew a text
 * input would carry that weight for every ordinary "are you sure" in the app.
 * Nothing here is recoverable — no soft delete, no export — so the gate is
 * deliberately more work than a second click.
 */
export default function DeleteAccountModal({
  open,
  isDeleting = false,
  error,
  onCancel,
  onConfirm,
}: DeleteAccountModalProps) {
  const titleId = useId()
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [typed, setTyped] = useState('')

  useEffect(() => {
    if (!open) {
      setTyped('')
      return
    }
    inputRef.current?.focus()
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && !isDeleting) onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, isDeleting, onCancel])

  if (!open) return null

  const armed = typed.trim().toUpperCase() === DELETE_CONFIRMATION

  return (
    <div
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isDeleting) onCancel()
      }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/20 p-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="my-auto max-h-[92dvh] w-full max-w-sm overflow-y-auto rounded-panel border border-border bg-card p-5 text-left sm:p-6"
      >
        <h2 id={titleId} className="font-serif text-lg font-medium text-teal-ink">
          Delete your account?
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
          This removes your profile, every job chat, every generated document,
          and your tracker — permanently, on the server, with no way to get any
          of it back.
        </p>

        <label
          htmlFor={inputId}
          className="mt-5 block text-[12px] font-medium text-text-primary"
        >
          Type <span className="font-mono text-coral-ink">{DELETE_CONFIRMATION}</span>{' '}
          to confirm
        </label>
        <input
          ref={inputRef}
          id={inputId}
          value={typed}
          disabled={isDeleting}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => setTyped(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && armed && !isDeleting) onConfirm()
          }}
          placeholder={DELETE_CONFIRMATION}
          className="mt-1.5 w-full rounded-input border border-border-input bg-bg px-3 py-2 text-[16px] text-text-primary outline-none transition-colors placeholder:text-text-faint focus:border-coral focus:bg-card disabled:opacity-60 sm:text-[13px]"
        />

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-input border border-coral/30 bg-coral-light px-3 py-2 text-[12px] leading-relaxed text-coral-ink"
          >
            {error}
          </p>
        )}

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={isDeleting}
            className="min-h-[42px] rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!armed || isDeleting}
            className="flex min-h-[42px] items-center justify-center gap-2 rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isDeleting && <Spinner size={14} className="text-white" />}
            {isDeleting ? 'Deleting...' : 'Delete my account'}
          </button>
        </div>
      </div>
    </div>
  )
}
