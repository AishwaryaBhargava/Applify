import api from './api'
import type { ChatMessage } from '../types'

/** GET /chats/{id}/messages — full message history for a chat. */
export async function listMessages(chatId: string): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>(`/chats/${chatId}/messages`)
  return data
}

/**
 * POST /chats/{id}/messages — sends a user message.
 * The response is streamed via SSE in Phase 6; this non-streaming helper
 * exists so the service surface matches the documented endpoints.
 */
export async function sendMessage(
  chatId: string,
  content: string,
): Promise<ChatMessage> {
  const { data } = await api.post<ChatMessage>(`/chats/${chatId}/messages`, {
    content,
  })
  return data
}

/** Absolute URL of the SSE endpoint consumed by useStream. */
export function messageStreamUrl(chatId: string): string {
  const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return `${base}/chats/${chatId}/messages`
}
