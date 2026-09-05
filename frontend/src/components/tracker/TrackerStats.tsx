import { CalendarCheck, Send, Table2, Trophy, type LucideIcon } from 'lucide-react'
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
 * Four numbers, in the order an application moves through them. "Applied"
 * counts everything that has left the house — an interview and an offer are
 * both applications that were sent — so the tiles never contradict each other
 * by shrinking as things go well.
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
]

/** The summary row above the table, drawn like the landing feature cards. */
export default function TrackerStats({ entries }: TrackerStatsProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {TILES.map(({ label, icon: Icon, iconClass, count }) => (
        <article
          key={label}
          className="rounded-card border border-border bg-card p-4"
        >
          <div
            className={`mb-2.5 flex h-8 w-8 items-center justify-center rounded-btn ${iconClass}`}
          >
            <Icon size={16} />
          </div>
          <div className="font-serif text-2xl font-medium text-teal-ink">
            {count(entries)}
          </div>
          <div className="mt-0.5 text-[12px] text-text-secondary">{label}</div>
        </article>
      ))}
    </div>
  )
}
