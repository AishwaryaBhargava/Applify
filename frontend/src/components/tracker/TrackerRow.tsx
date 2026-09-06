import type { MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import Badge from '../common/Badge'
import StatusPicker from './StatusPicker'
import { PRIORITY_DOT_CLASSES, PRIORITY_LABELS } from './statuses'
import {
  absoluteDateTime,
  daysAgoLabel,
  entryDate,
  entryTitle,
  relativeDate,
  shortDate,
} from '../../lib/format'
import type { TrackerEntry, TrackerStatus } from '../../types'

interface TrackerRowProps {
  entry: TrackerEntry
  onStatusChange?: (chatId: string, status: TrackerStatus) => void
  /** Opens the detail drawer — from the Details button or the row itself. */
  onOpen?: (chatId: string) => void
}

/** The em dash every empty cell uses, so a blank row still reads as a row. */
const EMPTY = '—'

/**
 * A click that landed on something with its own job — the title link, the
 * status dropdown, the Details button — is that control's, not the row's.
 * Without this, changing a status would also open the drawer behind it.
 */
function isInteractive(event: MouseEvent<HTMLTableRowElement>): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target?.closest('a, button, select, input, textarea, option'))
}

/** One application: everything about it, and the controls that change it. */
export default function TrackerRow({
  entry,
  onStatusChange,
  onOpen,
}: TrackerRowProps) {
  const added = entryDate(entry)
  const priority = entry.priority ?? null
  // The server computes this; a locally-created row has neither field yet.
  const appliedAgo =
    typeof entry.days_since_applied === 'number'
      ? entry.days_since_applied === 0
        ? 'today'
        : `${entry.days_since_applied} day${entry.days_since_applied === 1 ? '' : 's'} ago`
      : daysAgoLabel(entry.applied_at)

  return (
    <tr
      onClick={(event) => {
        if (!isInteractive(event)) onOpen?.(entry.chat_id)
      }}
      className="border-b border-border last:border-0 hover:bg-surface"
    >
      <td className="px-3 py-3">
        <span className="flex items-center gap-2">
          {priority && (
            <span
              aria-label={`${PRIORITY_LABELS[priority]} priority`}
              title={`${PRIORITY_LABELS[priority]} priority`}
              className={`h-2 w-2 flex-shrink-0 rounded-full ${PRIORITY_DOT_CLASSES[priority]}`}
            />
          )}
          <Link
            to={`/chat/${entry.chat_id}`}
            className="inline-flex min-h-[40px] items-center text-[13px] font-medium text-teal-ink hover:underline sm:min-h-0"
          >
            {entryTitle(entry)}
          </Link>
        </span>
      </td>

      <td className="px-3 py-3 text-[13px] text-text-secondary">
        {entry.company ?? EMPTY}
      </td>

      <td
        className="whitespace-nowrap px-3 py-3 text-[12px] text-text-muted"
        title={absoluteDateTime(added)}
      >
        {relativeDate(added) || EMPTY}
      </td>

      <td className="whitespace-nowrap px-3 py-3 text-[12px]">
        {entry.applied_at ? (
          <>
            <div className="text-text-secondary">
              {shortDate(entry.applied_at)}
            </div>
            {appliedAgo && (
              <div className="text-[11px] text-text-faint">{appliedAgo}</div>
            )}
          </>
        ) : (
          <span className="text-text-faint">{EMPTY}</span>
        )}
      </td>

      <td className="px-3 py-3 text-[12px]">
        {entry.next_action || entry.next_action_date ? (
          <div
            className={
              entry.next_action_due
                ? 'rounded-badge bg-amber-light px-1.5 py-1 text-amber-ink'
                : ''
            }
          >
            <div className="max-w-[170px] truncate text-text-secondary">
              {entry.next_action || 'Something to do'}
            </div>
            {entry.next_action_date && (
              <div
                className={`text-[11px] ${entry.next_action_due ? 'font-medium' : 'text-text-faint'}`}
              >
                {shortDate(entry.next_action_date)}
                {entry.next_action_due ? ' — due' : ''}
              </div>
            )}
          </div>
        ) : (
          <span className="text-text-faint">{EMPTY}</span>
        )}
      </td>

      <td className="px-3 py-3">
        {typeof entry.fit_score === 'number' ? (
          <span className="inline-block rounded-full bg-amber px-2.5 py-[3px] text-[12px] font-medium text-amber-ink">
            {entry.fit_score}
          </span>
        ) : (
          <span className="text-[12px] text-text-faint">{EMPTY}</span>
        )}
      </td>

      <td className="px-3 py-3">
        <Badge tone={entry.resume_type === 'tailored' ? 'teal' : 'neutral'}>
          {entry.resume_type === 'tailored' ? 'AI-tailored' : 'Unaltered'}
        </Badge>
      </td>

      <td className="px-3 py-3">
        <StatusPicker
          value={entry.status}
          onChange={(status) => onStatusChange?.(entry.chat_id, status)}
        />
      </td>

      {/*
        A chevron rather than the word "Details": the whole row already opens
        the drawer, so this is an affordance saying so, and nine columns of
        real information have a better claim on the width than a label for a
        control the row itself already is.
      */}
      <td className="px-1 py-3 text-right">
        <button
          type="button"
          onClick={() => onOpen?.(entry.chat_id)}
          aria-label={`Details for ${entryTitle(entry)}`}
          title="Details"
          className="inline-flex h-10 w-10 items-center justify-center rounded-input text-text-muted hover:bg-surface-warm hover:text-teal-deep sm:h-8 sm:w-8"
        >
          <ChevronRight size={15} />
        </button>
      </td>
    </tr>
  )
}
