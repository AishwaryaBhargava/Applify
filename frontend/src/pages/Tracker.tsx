import { useEffect } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import Spinner from '../components/common/Spinner'
import TrackerFilters from '../components/tracker/TrackerFilters'
import TrackerStats from '../components/tracker/TrackerStats'
import TrackerTable from '../components/tracker/TrackerTable'
import { useTrackerStore } from '../store/trackerStore'
import { useUiStore } from '../store/uiStore'

/**
 * The application pipeline: every job chat with its fit score, the resume that
 * went out, and where it stands.
 *
 * The rows are persisted from the last visit, so the table paints immediately
 * and the fetch reconciles it. A failed fetch leaves the old rows on screen
 * under a banner rather than blanking the page — the tracker is a record, and
 * a stale record still beats an empty one.
 */
export default function Tracker() {
  const entries = useTrackerStore((state) => state.entries)
  const filter = useTrackerStore((state) => state.filter)
  const isLoading = useTrackerStore((state) => state.isLoading)
  const error = useTrackerStore((state) => state.error)
  const setFilter = useTrackerStore((state) => state.setFilter)
  const fetchEntries = useTrackerStore((state) => state.fetchEntries)
  const updateStatus = useTrackerStore((state) => state.updateStatus)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)

  useEffect(() => {
    void fetchEntries({ force: true })
  }, [fetchEntries])

  const visible =
    filter === 'all'
      ? entries
      : entries.filter((entry) => entry.status === filter)

  return (
    <div className="flex h-full flex-col">
      <TopBar
        title="Application tracker"
        subtitle="Every role you have worked on, and where it stands"
        onMenu={toggleSidebar}
        actions={
          <button
            type="button"
            onClick={() => void fetchEntries({ force: true })}
            disabled={isLoading}
            className="flex min-h-[40px] items-center gap-1.5 rounded-btn border border-border-input bg-card px-3 py-1.5 text-[12px] font-medium text-text-secondary hover:border-teal-soft hover:text-teal-deep disabled:opacity-60 sm:min-h-0"
          >
            {isLoading ? <Spinner size={13} /> : <RefreshCw size={13} />}
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 md:px-8">
        <div className="mx-auto flex max-w-5xl flex-col gap-5">
          <TrackerStats entries={entries} />

          {error && (
            <div className="flex items-start gap-2.5 rounded-box bg-coral-light px-3.5 py-3 text-[13px] leading-relaxed text-coral-ink">
              <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
              <p>{error}</p>
            </div>
          )}

          <TrackerFilters
            entries={entries}
            value={filter}
            onChange={setFilter}
          />

          <TrackerTable
            entries={visible}
            isLoading={isLoading}
            isFiltered={filter !== 'all' && entries.length > 0}
            onStatusChange={(chatId, status) =>
              void updateStatus(chatId, status)
            }
          />
        </div>
      </div>
    </div>
  )
}
