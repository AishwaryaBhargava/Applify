import { ChevronDown } from 'lucide-react'
import { STATUS_CLASSES, STATUS_LABELS, STATUS_ORDER } from './statuses'
import type { TrackerStatus } from '../../types'

interface StatusPickerProps {
  value?: TrackerStatus
  onChange?: (status: TrackerStatus) => void
  disabled?: boolean
}

/**
 * The status dropdown, drawn as the badge it sets.
 *
 * A native `<select>` under a coloured pill: it keeps keyboard support, the
 * mobile wheel picker, and the accessible name for free, which a hand-rolled
 * menu would all have to earn back. The chevron is drawn separately because
 * `appearance-none` takes the platform one away with the platform styling.
 */
export default function StatusPicker({
  value = 'not_applied',
  onChange,
  disabled = false,
}: StatusPickerProps) {
  return (
    <span
      className={`relative inline-flex items-center rounded-pill text-[12px] font-medium ${STATUS_CLASSES[value]} ${disabled ? 'opacity-60' : ''}`}
    >
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange?.(event.target.value as TrackerStatus)}
        aria-label="Application status"
        className="min-h-[40px] cursor-pointer appearance-none rounded-pill bg-transparent py-[5px] pl-3 pr-7 text-[16px] text-inherit outline-none focus:ring-1 focus:ring-teal-deep disabled:cursor-default sm:min-h-0 sm:pl-2.5 sm:text-inherit"
      >
        {STATUS_ORDER.map((status) => (
          <option key={status} value={status} className="bg-card text-text-primary">
            {STATUS_LABELS[status]}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        aria-hidden="true"
        className="pointer-events-none absolute right-2 opacity-70"
      />
    </span>
  )
}
