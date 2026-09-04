import api from './api'
import type { Analysis, ChatMessage, JobChat } from '../types'

export interface ChatCreateRequest {
  title: string
  company: string
  jd_text: string
}

export interface ChatDetail extends JobChat {
  messages: ChatMessage[]
  analysis: Analysis | null
}

/** POST /chats — creates a chat and its tracker entry. */
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
