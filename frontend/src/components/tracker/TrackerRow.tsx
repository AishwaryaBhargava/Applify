import { Link } from 'react-router-dom'
import Badge from '../common/Badge'
import StatusPicker from './StatusPicker'
import type { TrackerEntry } from '../../types'

interface TrackerRowProps {
  entry: TrackerEntry
  onStatusChange?: (chatId: string, status: TrackerEntry['status']) => void
}

/** Single tracker row with status picker and resume type badge. */
export default function TrackerRow({ entry, onStatusChange }: TrackerRowProps) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-3 text-[13px]">
        <Link
          to={`/chat/${entry.chat_id}`}
          className="font-medium text-teal-ink hover:underline"
        >
          {entry.title ?? 'Untitled role'}
        </Link>
      </td>
      <td className="px-4 py-3 text-[13px] text-text-secondary">
        {entry.company ?? '—'}
      </td>
      <td className="px-4 py-3 text-[12px] text-text-muted">
        {entry.created_at}
      </td>
      <td className="px-4 py-3 text-[12px] text-text-muted">
        {entry.analysis_type ?? '—'}
      </td>
      <td className="px-4 py-3">
        <Badge tone={entry.resume_type === 'unaltered' ? 'neutral' : 'teal'}>
          {entry.resume_type === 'unaltered' ? 'Unaltered' : 'AI-Tailored'}
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
