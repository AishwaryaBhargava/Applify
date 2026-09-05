import type { ProfileGap } from '../../types'

interface ProfileGapNudgeProps {
  gap: ProfileGap
  onDismiss: (gapId: string) => void
}

/**
 * A soft suggestion for a missing or thin section, rendered directly above the
 * section it is about so the fix is one glance away. Dismissing it is
 * permanent until the next resume upload.
 */
export default function ProfileGapNudge({
  gap,
  onDismiss,
}: ProfileGapNudgeProps) {
  return (
    <div className="flex items-start gap-2.5 rounded-box border border-amber/30 bg-amber-light px-4 py-2.5">
      <span
        aria-hidden="true"
        className={`mt-[7px] h-[6px] w-[6px] flex-shrink-0 rounded-full ${
          gap.severity === 'missing' ? 'bg-amber' : 'bg-amber/60'
        }`}
      />
      <p className="flex-1 text-[12px] leading-relaxed text-amber-ink">
        {gap.message}
      </p>
      <button
        type="button"
        onClick={() => onDismiss(gap.id)}
        className="flex-shrink-0 text-[11px] font-medium text-amber-ink/80 underline-offset-2 hover:text-amber-ink hover:underline"
      >
        Dismiss
      </button>
    </div>
  )
}
