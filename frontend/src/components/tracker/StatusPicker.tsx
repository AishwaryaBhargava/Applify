import type { TrackerStatus } from '../../types'

interface StatusPickerProps {
  value?: TrackerStatus
  onChange?: (status: TrackerStatus) => void
}

const STATUS_LABELS: Record<TrackerStatus, string> = {
  not_applied: 'Not Applied',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
}

/**
 * Dropdown for updating application status.
 * TODO(Phase 8): call PATCH /tracker/{chat_id} through trackerStore.
 */
export default function StatusPicker({
  value = 'not_applied',
  onChange,
}: StatusPickerProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange?.(event.target.value as TrackerStatus)}
      className="rounded-input border border-border bg-card px-2.5 py-1.5 text-[12px] text-text-primary outline-none focus:border-teal-soft"
    >
      {(Object.keys(STATUS_LABELS) as TrackerStatus[]).map((status) => (
        <option key={status} value={status}>
          {STATUS_LABELS[status]}
        </option>
      ))}
    </select>
  )
}
