interface ConfirmModalProps {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm?: () => void
  onCancel?: () => void
}

/**
 * Generic confirmation dialog.
 * TODO(Phase 9): trap focus and close on Escape.
 */
export default function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4">
      <div className="w-full max-w-sm rounded-panel border border-border bg-card p-6">
        <h2 className="font-serif text-lg font-medium text-teal-ink">{title}</h2>
        {description && (
          <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
            {description}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
