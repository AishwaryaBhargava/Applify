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

/* ------------------------------------------------------------------ */
/* Tracker dates                                                       */
/* ------------------------------------------------------------------ */

/**
 * `YYYY-MM-DD` for a native `<input type="date">`, from either an ISO
 * timestamp or a date that is already in that shape.
 *
 * Deliberately built from the **local** calendar fields rather than
 * `toISOString().slice(0, 10)`: an applied_at of 23:30 on the 3rd is UTC's
 * 4th for anyone east of Greenwich, and a date input that reads a day later
 * than the timestamp beside it looks like a bug in the tracker.
 */
export function toDateInputValue(value: string | null | undefined): string {
  if (!value) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** A short calendar date — "3 Sep 2026" — for a `YYYY-MM-DD` or an ISO stamp. */
export function shortDate(value: string | null | undefined): string {
  if (!value) return ''
  // A bare date string is parsed as UTC midnight by the Date constructor, so
  // read it as local calendar fields instead of shifting it a day backwards.
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** Local midnight for a `YYYY-MM-DD` or ISO value, or null when unparseable. */
function startOfDay(value: string | null | undefined): Date | null {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  date.setHours(0, 0, 0, 0)
  return date
}

/**
 * Whole days from `value` until today: 0 today, 3 for three days ago, and a
 * negative number for a date still ahead. Null when there is no usable date.
 *
 * Counted in whole local days rather than elapsed milliseconds, so "applied
 * yesterday evening" is 1 day ago this morning rather than 0.
 */
export function daysSince(value: string | null | undefined): number | null {
  const then = startOfDay(value)
  if (!then) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((today.getTime() - then.getTime()) / (24 * 60 * 60 * 1000))
}

/** "today", "yesterday", "5 days ago", "in 3 days" — or '' with no date. */
export function daysAgoLabel(value: string | null | undefined): string {
  const days = daysSince(value)
  if (days === null) return ''
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days > 1) return `${days} days ago`
  return days === -1 ? 'tomorrow' : `in ${Math.abs(days)} days`
}

/**
 * Whether a next action falls inside the coming week — anything overdue, today,
 * or up to `days` ahead. This is what the "Due this week" tile counts, and an
 * action whose date has already passed is the most due thing there is.
 */
export function isDueWithin(
  value: string | null | undefined,
  days = 7,
): boolean {
  const elapsed = daysSince(value)
  if (elapsed === null) return false
  return elapsed >= -days
}
