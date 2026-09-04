import TopBar from '../components/common/TopBar'
import TrackerTable from '../components/tracker/TrackerTable'

/**
 * Job application tracker page.
 * TODO(Phase 8): fetch GET /tracker and add filter pills plus summary stats.
 */
export default function Tracker() {
  return (
    <div className="flex h-full flex-col">
      <TopBar title="Tracker" subtitle="Your full application pipeline" />
      <div className="flex-1 overflow-y-auto px-6 py-6 md:px-8">
        <TrackerTable />
      </div>
    </div>
  )
}
