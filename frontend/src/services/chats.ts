import api from './api'
import type { ChatDetail, JobChat } from '../types'

export interface ChatCreateRequest {
  title: string
  /** Optional on the backend; the new-chat modal still asks for it. */
  company?: string | null
  jd_text?: string | null
  /**
   * The three tracker fields worth capturing at the moment the user has the
   * posting open in another tab. They are copied onto the tracker entry the
   * same transaction opens, so filling them in here saves a trip to the
   * drawer later; leaving them out costs nothing.
   */
  job_url?: string | null
  location?: string | null
  source?: string | null
}

export type { ChatDetail }

/** POST /chats — creates a chat and, in the same transaction, its tracker entry. */
export async function createChat(payload: ChatCreateRequest): Promise<JobChat> {
  const { data } = await api.post<JobChat>('/chats', payload)
  return data
}

/** GET /chats — all chats for the current user, newest first. */
export async function listChats(): Promise<JobChat[]> {
  const { data } = await api.get<JobChat[]>('/chats')
  return data
}

/** GET /chats/{id} — a single chat with its messages and analysis. */
export async function getChat(id: string): Promise<ChatDetail> {
  const { data } = await api.get<ChatDetail>(`/chats/${id}`)
  return data
}

/** DELETE /chats/{id} — soft deletes a chat. */
export async function deleteChat(id: string): Promise<void> {
  await api.delete(`/chats/${id}`)
}
