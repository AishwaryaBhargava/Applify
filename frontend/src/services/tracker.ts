import api from './api'
import type {
  TrackerEntry,
  TrackerEntryPatch,
  TrackerSort,
  TrackerStatus,
} from '../types'

/** Query parameters `GET /tracker` understands. Every one is optional. */
export interface TrackerQuery {
  status?: TrackerStatus
  /** Free text over title, company and notes, matched server-side. */
  q?: string
  /** Always applied descending by the backend. */
  sort?: TrackerSort
}

/**
 * GET /tracker — every application, newest first unless `sort` says otherwise.
 *
 * The tracker page filters, searches and sorts the fetched rows in the browser
 * rather than round-tripping each keystroke: a user's application list is tens
 * of rows, not thousands, and a local filter is instant and works offline off
 * the persisted copy. The parameters exist for when that stops being true.
 */
export async function listTrackerEntries(
  query: TrackerQuery = {},
): Promise<TrackerEntry[]> {
  const params: Record<string, string> = {}
  if (query.status) params.status = query.status
  if (query.q?.trim()) params.q = query.q.trim()
  if (query.sort) params.sort = query.sort

  const { data } = await api.get<TrackerEntry[]>('/tracker', {
    ...(Object.keys(params).length ? { params } : {}),
  })
  return data
}

/**
 * PATCH /tracker/{chat_id} — writes any subset of the editable fields.
 *
 * Addressed by chat id, because that is what the user is looking at and what
 * ownership is checked against. The response is the **full** updated row, so a
 * caller replaces the entry with it rather than merging the patch: setting the
 * status to `applied` fills `applied_at` in server-side, and the recomputed
 * `days_since_applied` and `next_action_due` only come back this way.
 */
export async function updateTrackerEntry(
  chatId: string,
  patch: TrackerEntryPatch,
): Promise<TrackerEntry> {
  const { data } = await api.patch<TrackerEntry>(`/tracker/${chatId}`, patch)
  return data
}

/** PATCH /tracker/{chat_id} with only the status — the table's picker. */
export async function updateTrackerStatus(
  chatId: string,
  status: TrackerStatus,
): Promise<TrackerEntry> {
  return updateTrackerEntry(chatId, { status })
}
