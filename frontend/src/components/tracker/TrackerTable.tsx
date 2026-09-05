import { Link } from 'react-router-dom'
import { Table2 } from 'lucide-react'
import TrackerRow from './TrackerRow'
import type { TrackerEntry, TrackerStatus } from '../../types'

interface TrackerTableProps {
  entries?: TrackerEntry[]
  isLoading?: boolean
  onStatusChange?: (chatId: string, status: TrackerStatus) => void
  /** Shown when a filter, rather than an empty tracker, produced no rows. */
  isFiltered?: boolean
}

const COLUMNS = [
  'Job title',
  'Company',
  'Added',
  'Analysis',
  'Fit',
  'Resume',
  'Status',
]

/** Placeholder rows while the first fetch is in flight. */
function SkeletonRows() {
  return (
    <>
      {[0, 1, 2, 3].map((row) => (
        <tr key={row} className="border-b border-border last:border-0">
          {COLUMNS.map((column) => (
            <td key={column} className="px-4 py-3.5">
              <div className="h-3 animate-pulse rounded-badge bg-surface-warm" />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

/** Nothing to show: either the tracker is empty, or the filter is too narrow. */
function EmptyState({ isFiltered }: { isFiltered: boolean }) {
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
        className="mt-4 inline-block rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
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
  isFiltered = false,
}: TrackerTableProps) {
  const showEmpty = !isLoading && entries.length === 0

  return (
    <div className="overflow-hidden rounded-card border border-border bg-card">
      {showEmpty ? (
        <EmptyState isFiltered={isFiltered} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse text-left">
            <thead>
              <tr className="border-b border-border bg-surface">
                {COLUMNS.map((column) => (
                  <th
                    key={column}
                    scope="col"
                    className="px-4 py-3 text-[11px] font-medium tracking-[0.8px] text-text-muted"
                  >
                    {column.toUpperCase()}
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
