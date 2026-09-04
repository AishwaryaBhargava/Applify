export type ToastTone = 'info' | 'success' | 'error'

interface ToastProps {
  message: string
  tone?: ToastTone
  onDismiss?: () => void
}

const toneClasses: Record<ToastTone, string> = {
  info: 'bg-surface-warm text-text-primary border-border',
  success: 'bg-teal-light text-teal-ink border-teal-soft',
  error: 'bg-coral-light text-coral-ink border-coral',
}

/**
 * Non-blocking error and info notification.
 * TODO(Phase 9): drive from a toast store with auto-dismiss.
 */
export default function Toast({ message, tone = 'info', onDismiss }: ToastProps) {
  return (
    <div
      role="status"
      className={`flex items-center gap-3 rounded-box border px-4 py-3 text-[13px] shadow-sm ${toneClasses[tone]}`}
    >
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-[12px] font-medium underline-offset-2 hover:underline"
        >
          Dismiss
        </button>
      )}
    </div>
  )
}
