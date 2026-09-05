import { STATUS_LABELS, STATUS_ORDER } from './statuses'
import type { TrackerEntry, TrackerStatus } from '../../types'

export type TrackerFilter = TrackerStatus | 'all'

interface TrackerFiltersProps {
  entries: TrackerEntry[]
  value: TrackerFilter
  onChange: (filter: TrackerFilter) => void
}

/** Counts every pill needs, in one pass over the entries. */
function countsFor(entries: TrackerEntry[]): Record<TrackerFilter, number> {
  const counts = {
    all: entries.length,
    not_applied: 0,
    applied: 0,
    interviewing: 0,
    offer: 0,
    rejected: 0,
  } as Record<TrackerFilter, number>

  entries.forEach((entry) => {
    counts[entry.status] += 1
  })
  return counts
}

/**
 * The status filter, as pills carrying their own counts.
 *
 * The count is the point: it answers "how many am I waiting on" before the
 * user clicks anything, which is the question the tracker exists to answer.
 */
export default function TrackerFilters({
  entries,
  value,
  onChange,
}: TrackerFiltersProps) {
  const counts = countsFor(entries)
  const filters: TrackerFilter[] = ['all', ...STATUS_ORDER]

  return (
    /* The pills scroll sideways on a phone rather than wrapping to three rows
         that push the table below the fold. They wrap normally from 640px, where
         they all fit. */
    <div
      className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
      role="group"
      aria-label="Filter by status"
    >
      {filters.map((filter) => {
        const active = filter === value
        const label = filter === 'all' ? 'All' : STATUS_LABELS[filter]

        return (
          <button
            key={filter}
            type="button"
            onClick={() => onChange(filter)}
            aria-pressed={active}
            className={[
              'flex min-h-[40px] flex-shrink-0 snap-start items-center gap-1.5 rounded-pill px-3.5 py-1.5 text-[12px] font-medium transition-colors sm:min-h-0 sm:px-3',
              active
                ? 'bg-teal-light text-teal-ink'
                : 'border border-border bg-card text-text-secondary hover:bg-surface',
            ].join(' ')}
          >
            {label}
            <span className={active ? 'text-teal-deep' : 'text-text-faint'}>
              {counts[filter]}
            </span>
          </button>
        )
      })}
    </div>
  )
}
