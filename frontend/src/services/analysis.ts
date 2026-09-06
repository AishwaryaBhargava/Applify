import api from './api'
import type { Analysis, AnalysisType, KeywordMatch } from '../types'

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

/**
 * POST /chats/{id}/keywords — the ATS keyword match.
 *
 * Two calls in one endpoint, distinguished by `force`. Without it the stored
 * keyword list is reused and only the matching is re-run, which is what makes
 * "I added that skill to my profile, check again" free: the extraction is the
 * expensive half and the JD has not changed. `force=true` re-extracts from the
 * job description as well, for a posting that was edited or a first list the
 * user did not trust.
 *
 * `409` means there is no profile to match against — the same precondition
 * `/analyze` has, and the same resume nudge answers it.
 */
export async function runKeywordMatch(
  chatId: string,
  force = false,
): Promise<KeywordMatch> {
  const { data } = await api.post<KeywordMatch>(
    `/chats/${chatId}/keywords`,
    {},
    force ? { params: { force: true } } : undefined,
  )
  return data
}
