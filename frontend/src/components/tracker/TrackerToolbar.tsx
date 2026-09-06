import { useEffect, useState } from 'react'
import { ArrowUpDown, Search, X } from 'lucide-react'
import type { TrackerSort } from '../../types'

interface TrackerToolbarProps {
  /** The committed search term — what the table is actually filtered by. */
  search: string
  onSearchChange: (search: string) => void
  sort: TrackerSort
  onSortChange: (sort: TrackerSort) => void
  /** Rendered beside the count so an empty result explains itself. */
  resultCount: number
  totalCount: number
}

const SORT_LABELS: Record<TrackerSort, string> = {
  created_at: 'Newest',
  applied_at: 'Applied date',
  next_action_date: 'Next action',
  fit_score: 'Fit score',
}

const SORT_ORDER: TrackerSort[] = [
  'created_at',
  'applied_at',
  'next_action_date',
  'fit_score',
]

/** Long enough that a fast typist filters once, short enough to feel live. */
const DEBOUNCE_MS = 200

/**
 * Search and sort, above the table.
 *
 * The input keeps its own copy of the text and commits it on a timer, so every
 * keystroke redraws one small field rather than the whole table. The committed
 * value flows back down, which is what lets the clear button — and a filter
 * reset from elsewhere — empty the box.
 */
export default function TrackerToolbar({
  search,
  onSearchChange,
  sort,
  onSortChange,
  resultCount,
  totalCount,
}: TrackerToolbarProps) {
  const [draft, setDraft] = useState(search)

  // The committed value changing from outside (a clear, a reset) has to reach
  // the input; the guard is what stops that from fighting the debounce.
  useEffect(() => {
    setDraft((current) => (current === search ? current : search))
  }, [search])

  useEffect(() => {
    if (draft === search) return
    const timer = window.setTimeout(() => onSearchChange(draft), DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, onSearchChange, search])

  const filtering = search.trim().length > 0

  return (
    <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
      <div className="relative min-w-0 flex-1">
        <Search
          size={14}
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-faint"
        />
        <input
          type="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Search title, company or notes"
          aria-label="Search applications"
          className="min-h-[42px] w-full rounded-input border border-border-input bg-card py-2 pl-9 pr-9 text-[16px] outline-none focus:border-teal-deep sm:min-h-0 sm:text-[13px]"
        />
        {draft && (
          <button
            type="button"
            onClick={() => {
              setDraft('')
              onSearchChange('')
            }}
            aria-label="Clear search"
            className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-input text-text-faint hover:text-text-secondary"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <label className="relative flex items-center">
          <span className="sr-only">Sort applications by</span>
          <ArrowUpDown
            size={13}
            aria-hidden="true"
            className="pointer-events-none absolute left-3 text-text-faint"
          />
          <select
            value={sort}
            onChange={(event) =>
              onSortChange(event.target.value as TrackerSort)
            }
            className="min-h-[42px] appearance-none rounded-input border border-border-input bg-card py-2 pl-8 pr-8 text-[16px] outline-none focus:border-teal-deep sm:min-h-0 sm:text-[13px]"
          >
            {SORT_ORDER.map((option) => (
              <option key={option} value={option}>
                {SORT_LABELS[option]}
              </option>
            ))}
          </select>
        </label>

        {filtering && (
          <span className="flex-shrink-0 text-[12px] text-text-muted">
            {resultCount} of {totalCount}
          </span>
        )}
      </div>
    </div>
  )
}
