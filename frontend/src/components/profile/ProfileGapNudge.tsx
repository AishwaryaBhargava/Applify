import { Lightbulb } from 'lucide-react'
import type { ProfileGap } from '../../types'

interface ProfileGapNudgeProps {
  gap: ProfileGap
  onDismiss?: (gapId: string) => void
}

/**
 * Inline nudge when a profile section is thin.
 * TODO(Phase 5): persist dismissals to localStorage via profileStore.
 */
export default function ProfileGapNudge({
  gap,
  onDismiss,
}: ProfileGapNudgeProps) {
  return (
    <div className="flex items-start gap-2.5 rounded-box border border-amber/30 bg-amber-light px-4 py-3">
      <Lightbulb size={16} className="mt-0.5 flex-shrink-0 text-amber-ink" />
      <p className="flex-1 text-[12px] leading-relaxed text-amber-ink">
        {gap.message}
      </p>
      <button
        type="button"
        onClick={() => onDismiss?.(gap.id)}
        className="text-[11px] font-medium text-amber-ink underline-offset-2 hover:underline"
      >
        Dismiss
      </button>
    </div>
  )
}
