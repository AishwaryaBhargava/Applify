import api from './api'
import { streamSSE, type StreamHandlers } from './messages'
import type { GeneratedOutput, OutputType } from '../types'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface OutputRequest {
  output_type: OutputType
  /** A steer for a resume or cover letter; the question itself for an answer. */
  user_context?: string
}

/** Absolute URL of the SSE output endpoint. */
export function outputStreamUrl(chatId: string): string {
  return `${baseURL}/chats/${chatId}/outputs`
}

/**
 * POST /chats/{id}/outputs — the explicit-button path to a document.
 *
 * Answers with the same SSE stream as a chat message (start / token / done /
 * error), with `kind` fixed to the requested `output_type`, and persists the
 * user turn the button stands for before the first frame. So the only thing
 * this adds over `streamMessage` is the URL and the body.
 */
export async function streamOutput(
  chatId: string,
  payload: OutputRequest,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(outputStreamUrl(chatId), payload, handlers, signal)
}

/** GET /chats/{id}/outputs — documents already generated here, newest first. */
export async function listOutputs(chatId: string): Promise<GeneratedOutput[]> {
  const { data } = await api.get<GeneratedOutput[]>(`/chats/${chatId}/outputs`)
  return data
}
