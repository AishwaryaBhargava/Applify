import TrackerRow from './TrackerRow'
import type { TrackerEntry } from '../../types'

interface TrackerTableProps {
  entries?: TrackerEntry[]
}

const COLUMNS = [
  'Job title',
  'Company',
  'Date added',
  'Analysis',
  'Resume',
  'Status',
]

/**
 * Full tracker table.
 * TODO(Phase 8): fetch entries from trackerStore and support filter pills.
 */
export default function TrackerTable({ entries = [] }: TrackerTableProps) {
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-card">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <thead>
          <tr className="border-b border-border bg-surface">
            {COLUMNS.map((column) => (
              <th
                key={column}
                className="px-4 py-3 text-[11px] font-medium tracking-[0.8px] text-text-muted"
              >
                {column.toUpperCase()}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr>
              <td
                colSpan={COLUMNS.length}
                className="px-4 py-10 text-center text-[13px] text-text-muted"
              >
                No applications yet. Start a job chat to add one.
              </td>
            </tr>
          ) : (
            entries.map((entry) => <TrackerRow key={entry.id} entry={entry} />)
          )}
        </tbody>
      </table>
    </div>
  )
}
