import { useEffect, useState } from 'react'
import { getHealth } from '../../services/api'

type Status =
  | { state: 'loading' }
  | { state: 'ok'; value: string }
  | { state: 'error'; message: string }

/**
 * Phase 1 integration check: calls GET /health through services/api.ts on mount
 * and renders the result so the frontend-to-backend connection is testable in
 * the browser.
 */
export default function BackendStatus({ className = '' }: { className?: string }) {
  const [status, setStatus] = useState<Status>({ state: 'loading' })

  useEffect(() => {
    let cancelled = false

    getHealth()
      .then((data) => {
        if (!cancelled) setStatus({ state: 'ok', value: data.status })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof Error ? error.message : 'Unknown error'
        setStatus({ state: 'error', message })
      })

    return () => {
      cancelled = true
    }
  }, [])

  const dotClass =
    status.state === 'ok'
      ? 'bg-teal-medium'
      : status.state === 'error'
        ? 'bg-coral'
        : 'bg-text-faint'

  const label =
    status.state === 'loading'
      ? 'Backend: checking...'
      : status.state === 'ok'
        ? `Backend: ${status.value}`
        : `Backend: ${status.message}`

  return (
    <div
      className={`flex items-center gap-2 text-[11px] text-text-muted ${className}`}
      title={label}
    >
      <span className={`h-2 w-2 flex-shrink-0 rounded-full ${dotClass}`} />
      <span className="truncate">{label}</span>
    </div>
  )
}
