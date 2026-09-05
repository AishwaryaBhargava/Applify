export type AuthMessageTone = 'error' | 'success' | 'info'

interface AuthMessageProps {
  message: string
  tone?: AuthMessageTone
}

const toneClasses: Record<AuthMessageTone, string> = {
  error: 'bg-coral-light text-coral-ink border-coral/30',
  success: 'bg-teal-light text-teal-ink border-teal-soft',
  info: 'bg-amber-light text-amber-ink border-amber/30',
}

/**
 * Inline message region for the auth forms: validation problems, Supabase
 * errors, and confirmations such as "check your email".
 */
export default function AuthMessage({
  message,
  tone = 'error',
}: AuthMessageProps) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-input border px-3 py-2.5 text-[12px] leading-relaxed ${toneClasses[tone]}`}
    >
      {message}
    </div>
  )
}
