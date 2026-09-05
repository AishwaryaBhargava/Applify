import { Link } from 'react-router-dom'
import Badge from '../common/Badge'
import StatusPicker from './StatusPicker'
import { absoluteDateTime, entryDate, entryTitle, relativeDate } from '../../lib/format'
import type { AnalysisType, TrackerEntry, TrackerStatus } from '../../types'

interface TrackerRowProps {
  entry: TrackerEntry
  onStatusChange?: (chatId: string, status: TrackerStatus) => void
}

const ANALYSIS_LABELS: Record<AnalysisType, string> = {
  quick: 'Quick',
  detailed: 'Detailed',
}

/** The em dash every empty cell uses, so a blank row still reads as a row. */
const EMPTY = '—'

/** One application: everything about it, and the one control that changes it. */
export default function TrackerRow({ entry, onStatusChange }: TrackerRowProps) {
  const added = entryDate(entry)

  return (
    <tr className="border-b border-border last:border-0 hover:bg-surface">
      <td className="px-4 py-3">
        <Link
          to={`/chat/${entry.chat_id}`}
          className="text-[13px] font-medium text-teal-ink hover:underline"
        >
          {entryTitle(entry)}
        </Link>
      </td>

      <td className="px-4 py-3 text-[13px] text-text-secondary">
        {entry.company ?? EMPTY}
      </td>

      <td
        className="whitespace-nowrap px-4 py-3 text-[12px] text-text-muted"
        title={absoluteDateTime(added)}
      >
        {relativeDate(added) || EMPTY}
      </td>

      <td className="px-4 py-3">
        {entry.analysis_type ? (
          <Badge tone="neutral">{ANALYSIS_LABELS[entry.analysis_type]}</Badge>
        ) : (
          <span className="text-[12px] text-text-faint">{EMPTY}</span>
        )}
      </td>

      <td className="px-4 py-3">
        {typeof entry.fit_score === 'number' ? (
          <span className="inline-block rounded-full bg-amber px-2.5 py-[3px] text-[12px] font-medium text-amber-ink">
            {entry.fit_score}
          </span>
        ) : (
          <span className="text-[12px] text-text-faint">{EMPTY}</span>
        )}
      </td>

      <td className="px-4 py-3">
        <Badge tone={entry.resume_type === 'tailored' ? 'teal' : 'neutral'}>
          {entry.resume_type === 'tailored' ? 'AI-tailored' : 'Unaltered'}
        </Badge>
      </td>

      <td className="px-4 py-3">
        <StatusPicker
          value={entry.status}
          onChange={(status) => onStatusChange?.(entry.chat_id, status)}
        />
      </td>
    </tr>
  )
}
