import api from './api'
import type { Analysis, AnalysisType } from '../types'

/** POST /chats/{id}/analyze — runs a quick or detailed analysis. */
export async function runAnalysis(
  chatId: string,
  type: AnalysisType,
): Promise<Analysis> {
  const { data } = await api.post<Analysis>(`/chats/${chatId}/analyze`, { type })
  return data
}
