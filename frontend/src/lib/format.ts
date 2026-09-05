import type { TrackerEntry } from '../types'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const WEEK = 7 * DAY

/**
 * A short, glanceable age: "just now", "5m ago", "3h ago", "3d ago", "2w ago",
 * and a plain date past a month. Returns '' for a missing or unparseable
 * timestamp so a caller can fall back rather than print "Invalid Date".
 */
export function relativeDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''

  const elapsed = Date.now() - then
  // A clock a little behind the server reads as the future; call that "now".
  if (elapsed < MINUTE) return 'just now'
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)}m ago`
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)}h ago`
  if (elapsed < WEEK) return `${Math.floor(elapsed / DAY)}d ago`
  if (elapsed < 5 * WEEK) return `${Math.floor(elapsed / WEEK)}w ago`
  return absoluteDate(iso, { month: 'short' })
}

/** The full timestamp, for a title attribute behind the relative one. */
export function absoluteDate(
  iso: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    ...options,
  })
}

/** The full date and time, used as the hover title on a relative date. */
export function absoluteDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * "Kestrel Labs" -> "Kestrel-Labs". Used to name a downloaded document after
 * the company it was written for.
 */
export function slugify(text: string, fallback = 'applify'): string {
  const slug = text
    .normalize('NFKD')
    // Strip accents, then anything that is not a word character or a space.
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-{2,}/g, '-')
  return slug || fallback
}

/**
 * The row's job title. The server sends `job_title`; the optimistic row the
 * sidebar writes when a chat is created carries the Phase 6 `title`.
 */
export function entryTitle(entry: TrackerEntry): string {
  return entry.job_title ?? entry.title ?? 'Untitled role'
}

/**
 * When the application was started. `date_added` is the chat's creation time;
 * `created_at` is the tracker row's own, and the two normally match.
 */
export function entryDate(entry: TrackerEntry): string {
  return entry.date_added ?? entry.created_at
}
