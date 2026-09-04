import api from './api'
import type { GeneratedOutput, OutputType } from '../types'

export interface OutputRequest {
  output_type: OutputType
  user_context?: string
}

/** POST /chats/{id}/outputs — generates a resume, cover letter, or answer. */
export async function generateOutput(
  chatId: string,
  payload: OutputRequest,
): Promise<GeneratedOutput> {
  const { data } = await api.post<GeneratedOutput>(
    `/chats/${chatId}/outputs`,
    payload,
  )
  return data
}

/** Absolute URL of the SSE output endpoint consumed by useStream. */
export function outputStreamUrl(chatId: string): string {
  const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return `${base}/chats/${chatId}/outputs`
}
