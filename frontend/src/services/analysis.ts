import api from './api'
import type { Analysis, AnalysisType } from '../types'

/**
 * POST /chats/{id}/analyze — runs a quick or detailed analysis.
 *
 * The backend returns the stored analysis untouched when one already exists,
 * so a revisit never costs a model call and never shows a different score for
 * the same profile and JD. `force` is the explicit opt-in to re-run and
 * replace it, sent as a query parameter.
 */
export async function runAnalysis(
  chatId: string,
  analysisType: AnalysisType,
  force = false,
): Promise<Analysis> {
  const { data } = await api.post<Analysis>(
    `/chats/${chatId}/analyze`,
    { analysis_type: analysisType },
    force ? { params: { force: true } } : undefined,
  )
  return data
}
