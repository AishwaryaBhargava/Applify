import type { ProfileGap } from '../../types'

/** A missing section costs more than a thin one, and nothing costs everything. */
const MISSING_PENALTY = 12
const THIN_PENALTY = 6

interface ProfileCompletenessProps {
  gaps: ProfileGap[]
}

/**
 * How complete the profile is, scored from the backend's own gap detection so
 * the bar and the nudges can never disagree.
 *
 * 100 minus 12 per missing section and 6 per thin one, clamped to 0-100.
 */
function completenessPercent(gaps: ProfileGap[]): number {
  const penalty = gaps.reduce(
    (total, gap) =>
      total + (gap.severity === 'missing' ? MISSING_PENALTY : THIN_PENALTY),
    0,
  )
  return Math.min(100, Math.max(0, 100 - penalty))
}

/**
 * The completeness bar above the profile sections. Always rendered, including
 * at 100%, so the page never loses its summary line as the user fills gaps in.
 */
export default function ProfileCompleteness({
  gaps,
}: ProfileCompletenessProps) {
  const percent = completenessPercent(gaps)
  const count = gaps.length

  return (
    <section className="rounded-card border border-border bg-card px-5 py-4">
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-serif text-[15px] font-medium text-teal-ink">
          Profile completeness
        </h2>
        <p className="text-[12px] text-text-secondary">
          <span className="font-medium text-text-primary">{percent}% complete</span>
          {' · '}
          {count === 0
            ? 'every section covered'
            : `${count} suggestion${count === 1 ? '' : 's'}`}
        </p>
      </div>

      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Profile completeness"
        className="h-2 w-full overflow-hidden rounded-full bg-teal-light"
      >
        <div
          className="h-full rounded-full bg-teal-medium transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>

      <p className="mt-2.5 text-[12px] leading-relaxed text-text-muted">
        {count === 0
          ? 'Nothing outstanding. Every analysis and generated document draws on all of this.'
          : 'The richer this profile, the more grounded every analysis and generated document is.'}
      </p>
    </section>
  )
}
