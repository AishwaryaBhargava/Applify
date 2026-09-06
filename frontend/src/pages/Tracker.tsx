import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import Spinner from '../components/common/Spinner'
import TrackerDrawer from '../components/tracker/TrackerDrawer'
import TrackerFilters from '../components/tracker/TrackerFilters'
import TrackerStats from '../components/tracker/TrackerStats'
import TrackerTable from '../components/tracker/TrackerTable'
import TrackerToolbar from '../components/tracker/TrackerToolbar'
import { entryDate, entryTitle } from '../lib/format'
import { useTrackerStore } from '../store/trackerStore'
import { useUiStore } from '../store/uiStore'
import type { TrackerEntry, TrackerSort } from '../types'

/** Everything the search box looks at, lower-cased once per row. */
function haystack(entry: TrackerEntry): string {
  return [
    entryTitle(entry),
    entry.company ?? '',
    entry.notes ?? '',
    entry.location ?? '',
    entry.next_action ?? '',
  ]
    .join(' ')
    .toLowerCase()
}

/** Milliseconds for a sortable date, or null when there is nothing to sort by. */
function timeOf(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

/**
 * Sorts a copy of the rows, descending, with the rows that have nothing to
 * sort by pushed to the bottom.
 *
 * That last part is the whole reason this is not a one-line comparator. Sorting
 * by applied date puts a row that was never applied to nowhere in particular
 * unless it is told where to go, and "at the end" is the only answer that keeps
 * the top of the list meaningful.
 */
function sortEntries(entries: TrackerEntry[], sort: TrackerSort): TrackerEntry[] {
  const keyOf = (entry: TrackerEntry): number | null => {
    switch (sort) {
      case 'applied_at':
        return timeOf(entry.applied_at)
      case 'next_action_date':
        return timeOf(entry.next_action_date)
      case 'fit_score':
        return typeof entry.fit_score === 'number' ? entry.fit_score : null
      default:
        return timeOf(entryDate(entry))
    }
  }

  return [...entries].sort((a, b) => {
    const left = keyOf(a)
    const right = keyOf(b)
    if (left === null && right === null) return 0
    if (left === null) return 1
    if (right === null) return -1
    // Ascending for the next action: the thing due soonest is the thing to do,
    // and burying it under everything scheduled for next month is backwards.
    return sort === 'next_action_date' ? left - right : right - left
  })
}

/**
 * The application pipeline: every job chat with its fit score, the resume that
 * went out, where it stands, and what it needs next.
 *
 * The rows are persisted from the last visit, so the table paints immediately
 * and the fetch reconciles it. A failed fetch leaves the old rows on screen
 * under a banner rather than blanking the page — the tracker is a record, and
 * a stale record still beats an empty one.
 *
 * Filtering, searching and sorting all happen here rather than through the
 * API. A user's tracker is tens of rows: a local pass is instant, works off
 * the persisted copy while the backend is unreachable, and does not spend a
 * request per keystroke.
 */
export default function Tracker() {
  const entries = useTrackerStore((state) => state.entries)
  const filter = useTrackerStore((state) => state.filter)
  const search = useTrackerStore((state) => state.search)
  const sort = useTrackerStore((state) => state.sort)
  const isLoading = useTrackerStore((state) => state.isLoading)
  const savingChatId = useTrackerStore((state) => state.savingChatId)
  const error = useTrackerStore((state) => state.error)
  const setFilter = useTrackerStore((state) => state.setFilter)
  const setSearch = useTrackerStore((state) => state.setSearch)
  const setSort = useTrackerStore((state) => state.setSort)
  const fetchEntries = useTrackerStore((state) => state.fetchEntries)
  const updateStatus = useTrackerStore((state) => state.updateStatus)
  const patchEntry = useTrackerStore((state) => state.patchEntry)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)

  const [openChatId, setOpenChatId] = useState<string | null>(null)

  useEffect(() => {
    void fetchEntries({ force: true })
  }, [fetchEntries])

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    const filtered = entries.filter((entry) => {
      if (filter !== 'all' && entry.status !== filter) return false
      if (term && !haystack(entry).includes(term)) return false
      return true
    })
    return sortEntries(filtered, sort)
  }, [entries, filter, search, sort])

  // Read from the live list rather than held in state: an optimistic status
  // change or a finished resume has to reach the open drawer, and a snapshot
  // taken when the row was clicked would not.
  const openEntry =
    entries.find((entry) => entry.chat_id === openChatId) ?? null

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
        <div className="mx-auto flex max-w-6xl flex-col gap-5">
          <TrackerStats entries={entries} />

          {error && (
            <div className="flex items-start gap-2.5 rounded-box bg-coral-light px-3.5 py-3 text-[13px] leading-relaxed text-coral-ink">
              <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
              <p>{error}</p>
            </div>
          )}

          <TrackerToolbar
            search={search}
            onSearchChange={setSearch}
            sort={sort}
            onSortChange={setSort}
            resultCount={visible.length}
            totalCount={entries.length}
          />

          <TrackerFilters
            entries={entries}
            value={filter}
            onChange={setFilter}
          />

          <TrackerTable
            entries={visible}
            isLoading={isLoading}
            isFiltered={filter !== 'all' && entries.length > 0}
            isSearching={search.trim().length > 0 && entries.length > 0}
            onStatusChange={(chatId, status) =>
              void updateStatus(chatId, status)
            }
            onOpen={setOpenChatId}
          />
        </div>
      </div>

      <TrackerDrawer
        entry={openEntry}
        open={openEntry !== null}
        onClose={() => setOpenChatId(null)}
        onSave={patchEntry}
        isSaving={savingChatId === openChatId}
      />
    </div>
  )
}
