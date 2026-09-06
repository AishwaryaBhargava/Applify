import {
  CalendarClock,
  CalendarCheck,
  Send,
  Table2,
  Trophy,
  type LucideIcon,
} from 'lucide-react'
import { isDueWithin } from '../../lib/format'
import type { TrackerEntry } from '../../types'

interface TrackerStatsProps {
  entries: TrackerEntry[]
}

interface Tile {
  label: string
  icon: LucideIcon
  iconClass: string
  count: (entries: TrackerEntry[]) => number
}

/**
 * Five numbers, in the order an application moves through them. "Applied"
 * counts everything that has left the house — an interview and an offer are
 * both applications that were sent — so the tiles never contradict each other
 * by shrinking as things go well.
 *
 * "Due this week" is the odd one out and is the point of the row: the other
 * four describe the past, and it is the only one that asks for something.
 */
const TILES: Tile[] = [
  {
    label: 'Total',
    icon: Table2,
    iconClass: 'bg-surface-warm text-text-secondary',
    count: (entries) => entries.length,
  },
  {
    label: 'Applied',
    icon: Send,
    iconClass: 'bg-teal-light text-teal-deep',
    count: (entries) =>
      entries.filter((entry) => entry.status !== 'not_applied').length,
  },
  {
    label: 'Interviewing',
    icon: CalendarCheck,
    iconClass: 'bg-amber-light text-amber-ink',
    count: (entries) =>
      entries.filter((entry) => entry.status === 'interviewing').length,
  },
  {
    label: 'Offers',
    icon: Trophy,
    iconClass: 'bg-coral-light text-coral',
    count: (entries) => entries.filter((entry) => entry.status === 'offer').length,
  },
  {
    label: 'Due this week',
    icon: CalendarClock,
    iconClass: 'bg-amber-light text-amber-ink',
    // `next_action_due` is the server's word for "today or overdue"; anything
    // it has not flagged is checked against the coming seven days here. An
    // overdue action counts as due — it is the most due thing there is.
    count: (entries) =>
      entries.filter(
        (entry) =>
          entry.next_action_due || isDueWithin(entry.next_action_date, 7),
      ).length,
  },
]

/** The summary row above the table, drawn like the landing feature cards. */
export default function TrackerStats({ entries }: TrackerStatsProps) {
  return (
    /* Two up on a phone, three from 640px, all five in a row at desktop —
       five never divides into two columns without an orphan, and the odd tile
       out is the one that asks for something. */
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3 lg:grid-cols-5">
      {TILES.map(({ label, icon: Icon, iconClass, count }) => (
        <article
          key={label}
          className="rounded-card border border-border bg-card p-3.5 sm:p-4"
        >
          <div
            className={`mb-2.5 flex h-8 w-8 items-center justify-center rounded-btn ${iconClass}`}
          >
            <Icon size={16} />
          </div>
          <div className="font-serif text-[22px] font-medium text-teal-ink sm:text-2xl">
            {count(entries)}
          </div>
          <div className="mt-0.5 text-[12px] text-text-secondary">{label}</div>
        </article>
      ))}
    </div>
  )
}
