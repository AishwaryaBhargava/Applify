import TopBar from '../components/common/TopBar'

/**
 * Account and app settings.
 * TODO(Phase 9): account details, sign out, and data controls.
 */
export default function Settings() {
  return (
    <div className="flex h-full flex-col">
      <TopBar title="Settings" subtitle="Account and preferences" />
      <div className="flex-1 overflow-y-auto px-6 py-6 md:px-8">
        <div className="mx-auto max-w-2xl rounded-card border border-border bg-card p-6 text-[13px] text-text-secondary">
          Settings arrive in a later phase.
        </div>
      </div>
    </div>
  )
}
