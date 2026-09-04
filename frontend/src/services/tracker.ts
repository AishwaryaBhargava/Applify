import api from './api'
import type { TrackerEntry, TrackerStatus } from '../types'

/** GET /tracker — all tracker entries for the current user. */
export async function listTrackerEntries(): Promise<TrackerEntry[]> {
  const { data } = await api.get<TrackerEntry[]>('/tracker')
  return data
}

/** PATCH /tracker/{chat_id} — updates the status of one entry. */
export async function updateTrackerStatus(
  chatId: string,
  status: TrackerStatus,
): Promise<TrackerEntry> {
  const { data } = await api.patch<TrackerEntry>(`/tracker/${chatId}`, {
    status,
  })
  return data
}
