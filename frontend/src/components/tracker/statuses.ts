import type { TrackerPriority, TrackerStatus } from '../../types'

export const STATUS_LABELS: Record<TrackerStatus, string> = {
  not_applied: 'Not applied',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
}

/** The five statuses in pipeline order — the order the filter pills use too. */
export const STATUS_ORDER: TrackerStatus[] = [
  'not_applied',
  'applied',
  'interviewing',
  'offer',
  'rejected',
]

/**
 * A status carries its own colour so the pipeline reads down the column
 * without anyone having to read the words: neutral until it is sent, teal once
 * it is, amber while it is live, a filled teal for an offer, coral for a no.
 */
export const STATUS_CLASSES: Record<TrackerStatus, string> = {
  not_applied: 'bg-surface-warm text-text-secondary',
  applied: 'bg-teal-light text-teal-ink',
  interviewing: 'bg-amber-light text-amber-ink',
  offer: 'bg-teal-medium text-white',
  rejected: 'bg-coral-light text-coral-ink',
}

/* ------------------------------------------------------------------ */
/* Priority                                                            */
/* ------------------------------------------------------------------ */

export const PRIORITY_LABELS: Record<TrackerPriority, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/** Highest first — the order a picker should offer them in. */
export const PRIORITY_ORDER: TrackerPriority[] = ['high', 'medium', 'low']

/**
 * The dot beside a title, in the sidebar and in the table.
 *
 * Only high and medium get a colour. A low priority is a decision the user
 * made, but it is not something to draw attention to, and a dot on every row
 * is a dot that says nothing — so low is drawn as a hollow outline and an
 * unset priority gets no dot at all.
 */
export const PRIORITY_DOT_CLASSES: Record<TrackerPriority, string> = {
  high: 'bg-coral',
  medium: 'bg-amber',
  low: 'border border-border-input bg-transparent',
}

/** Chip colours for the priority as the drawer and the row render it. */
export const PRIORITY_CLASSES: Record<TrackerPriority, string> = {
  high: 'bg-coral-light text-coral-ink',
  medium: 'bg-amber-light text-amber-ink',
  low: 'bg-surface-warm text-text-secondary',
}
