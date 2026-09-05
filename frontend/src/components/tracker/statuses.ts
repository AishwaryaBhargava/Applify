import type { TrackerStatus } from '../../types'

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
