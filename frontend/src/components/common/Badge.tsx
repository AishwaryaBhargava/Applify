import type { ReactNode } from 'react'

export type BadgeTone = 'teal' | 'coral' | 'amber' | 'neutral'

interface BadgeProps {
  children: ReactNode
  tone?: BadgeTone
  className?: string
}

const toneClasses: Record<BadgeTone, string> = {
  teal: 'bg-teal-light text-teal-ink',
  coral: 'bg-coral-light text-coral-ink',
  amber: 'bg-amber-light text-amber-ink',
  neutral: 'bg-surface-warm text-text-secondary',
}

/** Status badge (Applied, Interviewing, AI-Tailored, ...). */
export default function Badge({
  children,
  tone = 'neutral',
  className = '',
}: BadgeProps) {
  return (
    <span
      className={`inline-block rounded-pill px-2 py-[3px] text-[11px] font-medium ${toneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
