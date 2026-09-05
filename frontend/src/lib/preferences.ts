import type { AnalysisType } from '../types'

const DEFAULT_ANALYSIS_KEY = 'applify-default-analysis'

/** The depth a new chat's picker highlights, before the user chooses. */
export const DEFAULT_ANALYSIS_TYPE: AnalysisType = 'quick'

/**
 * Preferences that only this browser needs to know.
 *
 * Deliberately localStorage rather than a column on the user: nothing on the
 * server behaves differently because of it, and a preference that needs a
 * migration to add is a preference that will not get added. Every read is
 * defensive — private mode, a cleared store, or a value written by an older
 * build all have to resolve to the default rather than throw.
 */
export function readDefaultAnalysisType(): AnalysisType {
  try {
    const value = window.localStorage.getItem(DEFAULT_ANALYSIS_KEY)
    return value === 'quick' || value === 'detailed'
      ? value
      : DEFAULT_ANALYSIS_TYPE
  } catch {
    return DEFAULT_ANALYSIS_TYPE
  }
}

export function writeDefaultAnalysisType(value: AnalysisType): void {
  try {
    window.localStorage.setItem(DEFAULT_ANALYSIS_KEY, value)
  } catch {
    // Storage unavailable: the choice holds for this session only.
  }
}
