import { useEffect, useId, useRef } from 'react'

interface ConfirmModalProps {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  /** `danger` is the destructive coral; `primary` the ordinary teal action. */
  tone?: 'danger' | 'primary'
  onConfirm?: () => void
  onCancel?: () => void
}

/**
 * Generic confirmation dialog.
 *
 * Escape and a click on the backdrop both cancel, and focus moves to Cancel on
 * open — the safe default for a dialog whose other button is usually
 * destructive, and what makes the dialog usable without a mouse.
 */
export default function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onCancel?.()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!open) return null

  const confirmClasses =
    tone === 'danger'
      ? 'bg-coral hover:opacity-90'
      : 'bg-teal-deep hover:opacity-90'

  return (
    <div
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel?.()
      }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/20 p-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="my-auto max-h-[92dvh] w-full max-w-sm overflow-y-auto rounded-panel border border-border bg-card p-5 text-left sm:p-6"
      >
        <h2
          id={titleId}
          className="font-serif text-lg font-medium text-teal-ink"
        >
          {title}
        </h2>
        {description && (
          <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
            {description}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="min-h-[42px] rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-teal-soft hover:text-teal-ink"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`min-h-[42px] rounded-btn px-4 py-2 text-[13px] font-medium text-white transition-opacity ${confirmClasses}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
