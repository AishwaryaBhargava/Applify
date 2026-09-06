import { Link } from 'react-router-dom'
import { Table2 } from 'lucide-react'
import TrackerRow from './TrackerRow'
import type { TrackerEntry, TrackerStatus } from '../../types'

interface TrackerTableProps {
  entries?: TrackerEntry[]
  isLoading?: boolean
  onStatusChange?: (chatId: string, status: TrackerStatus) => void
  /** Opens the detail drawer for one row. */
  onOpen?: (chatId: string) => void
  /** Shown when a filter, rather than an empty tracker, produced no rows. */
  isFiltered?: boolean
  /** True when the empty result is a search miss rather than a status filter. */
  isSearching?: boolean
}

/**
 * The analysis depth used to have a column of its own. It moved into the
 * drawer when the pipeline fields arrived: "quick or detailed" is a footnote
 * about how a score was produced, and the two things it was displacing —
 * when the application went out, and what you owe it next — are the questions
 * a tracker exists to answer at a glance.
 */
const COLUMNS = [
  'Job title',
  'Company',
  'Added',
  'Applied',
  'Next action',
  'Fit',
  'Resume',
  'Status',
  '',
]

/**
 * Placeholder rows while the first fetch is in flight. The pulse is put on the
 * row rather than each cell so a row breathes as one object, matching the
 * profile and analysis skeletons.
 */
function SkeletonRows() {
  return (
    <>
      {[0, 1, 2, 3].map((row) => (
        <tr
          key={row}
          aria-hidden="true"
          className="animate-pulse border-b border-border last:border-0"
        >
          {COLUMNS.map((column, index) => (
            <td key={column || `spacer-${index}`} className="px-3 py-3.5">
              <div className="h-3 rounded-badge bg-surface-warm" />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

/** Nothing to show: either the tracker is empty, or the filter is too narrow. */
function EmptyState({
  isFiltered,
  isSearching,
}: {
  isFiltered: boolean
  isSearching: boolean
}) {
  if (isSearching) {
    return (
      <div className="px-4 py-12 text-center">
        <p className="text-[13px] text-text-secondary">
          Nothing matches that search.
        </p>
      </div>
    )
  }

  if (isFiltered) {
    return (
      <div className="px-4 py-12 text-center">
        <p className="text-[13px] text-text-secondary">
          No applications at this status yet.
        </p>
      </div>
    )
  }

  return (
    <div className="px-4 py-12 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-btn bg-teal-light">
        <Table2 size={20} className="text-teal-deep" />
      </div>
      <h2 className="font-serif text-lg font-medium text-teal-ink">
        No applications yet
      </h2>
      <p className="mx-auto mt-1.5 max-w-sm text-[13px] leading-relaxed text-text-secondary">
        Every job chat you start lands here with its fit score, the resume you
        sent, and where the application stands.
      </p>
      <Link
        to="/chat"
        className="mt-4 inline-flex min-h-[44px] items-center rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
      >
        Start a job chat
      </Link>
    </div>
  )
}

/**
 * The application pipeline as a table.
 *
 * The whole table scrolls sideways inside its own card below about 800px
 * rather than pushing the page wide: a horizontal scrollbar on the body would
 * move the sidebar and the filter pills too.
 */
export default function TrackerTable({
  entries = [],
  isLoading = false,
  onStatusChange,
  onOpen,
  isFiltered = false,
  isSearching = false,
}: TrackerTableProps) {
  const showEmpty = !isLoading && entries.length === 0

  return (
    <div className="overflow-hidden rounded-card border border-border bg-card">
      {showEmpty ? (
        <EmptyState isFiltered={isFiltered} isSearching={isSearching} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-collapse text-left">
            <thead>
              <tr className="border-b border-border bg-surface">
                {COLUMNS.map((column, index) => (
                  <th
                    key={column || `spacer-${index}`}
                    scope="col"
                    className={`whitespace-nowrap px-3 py-3 text-[11px] font-medium tracking-[0.8px] text-text-muted ${
                      column === 'Job title'
                        ? 'min-w-[200px]'
                        : column === 'Company'
                          ? 'min-w-[130px]'
                          : column === 'Next action'
                            ? 'min-w-[170px]'
                            : ''
                    }`}
                  >
                    {/* The last column holds the Details button; a heading over
                        it would be a word describing a chevron. */}
                    {column ? column.toUpperCase() : <span className="sr-only">Details</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && entries.length === 0 ? (
                <SkeletonRows />
              ) : (
                entries.map((entry) => (
                  <TrackerRow
                    key={entry.chat_id}
                    entry={entry}
                    onStatusChange={onStatusChange}
                    onOpen={onOpen}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
