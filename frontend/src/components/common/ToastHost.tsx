import Toast from './Toast'
import { useToastStore } from '../../store/toastStore'

/**
 * The one place toasts are drawn: bottom-right, above everything, and never in
 * the way of the composer. Mounted once in the app shell so any store action
 * can raise a toast without a component in the middle.
 */
export default function ToastHost() {
  const toasts = useToastStore((state) => state.toasts)
  const dismiss = useToastStore((state) => state.dismiss)

  if (toasts.length === 0) return null

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            message={toast.message}
            tone={toast.tone}
            onDismiss={() => dismiss(toast.id)}
          />
        </div>
      ))}
    </div>
  )
}
