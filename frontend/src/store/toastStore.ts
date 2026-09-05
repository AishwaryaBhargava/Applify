import { create } from 'zustand'
import type { ToastTone } from '../components/common/Toast'

export interface ToastItem {
  id: string
  message: string
  tone: ToastTone
}

/** How long a toast stays before it dismisses itself. */
const TOAST_MS = 4000

/** Timers keyed by toast id, so a manual dismiss can cancel its own. */
const timers = new Map<string, ReturnType<typeof setTimeout>>()

function toastId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/**
 * Transient notifications: "Tracker updated", "That status did not save".
 *
 * Deliberately not persisted — a toast that survives a reload is describing
 * something that already finished. The queue is capped at three so a burst of
 * failures cannot cover the page it is reporting on.
 */
export interface ToastState {
  toasts: ToastItem[]
  /** Shows a toast and returns its id. Auto-dismisses after four seconds. */
  push: (message: string, tone?: ToastTone) => string
  dismiss: (id: string) => void
  clear: () => void
}

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  push: (message, tone = 'info') => {
    const id = toastId()
    set((state) => ({ toasts: [...state.toasts, { id, message, tone }].slice(-3) }))
    timers.set(
      id,
      setTimeout(() => get().dismiss(id), TOAST_MS),
    )
    return id
  },

  dismiss: (id) => {
    const timer = timers.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.delete(id)
    }
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
  },

  clear: () => {
    timers.forEach((timer) => clearTimeout(timer))
    timers.clear()
    set({ toasts: [] })
  },
}))

/**
 * Shows a toast from outside React — a store action, a stream handler. The
 * component-facing path is `useToastStore((state) => state.push)`.
 */
export function pushToast(message: string, tone: ToastTone = 'info'): string {
  return useToastStore.getState().push(message, tone)
}

export default useToastStore
