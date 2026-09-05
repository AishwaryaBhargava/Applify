import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Check, ChevronDown, ChevronRight, RefreshCw, X } from 'lucide-react'
import Spinner from '../common/Spinner'
import type { Analysis, DetailedSkill } from '../../types'

interface AnalysisCardProps {
  analysis: Analysis
  /** Rendered into the header line: "Fit analysis — {title}, {company}". */
  title: string
  company?: string | null
  onRerun?: () => void
  isRerunning?: boolean
}

/** The skills array, only when the payload actually carries usable ones. */
function skillsOf(analysis: Analysis): DetailedSkill[] {
  const skills = analysis.full_json?.skills
  if (!Array.isArray(skills)) return []
  return skills.filter((skill) => Boolean(skill?.skill))
}

/** A yes/no cell: a teal check or a muted cross, never a bare boolean. */
function Mark({ on, label }: { on: boolean; label: string }) {
  return on ? (
    <Check size={14} className="text-teal-medium" aria-label={`${label}: yes`} />
  ) : (
    <X size={14} className="text-text-faint" aria-label={`${label}: no`} />
  )
}

/**
 * The fit analysis, as the product mockup draws it: a score pill, strengths as
 * teal tags, gaps as coral tags, and the verdict underneath. A detailed
 * breakdown adds the skill-by-skill table and the narrative, collapsed by
 * default so the summary stays the thing you read first.
 */
export default function AnalysisCard({
  analysis,
  title,
  company,
  onRerun,
  isRerunning = false,
}: AnalysisCardProps) {
  const [showSkills, setShowSkills] = useState(false)
  const skills = skillsOf(analysis)
  const narrative = analysis.full_json?.narrative ?? ''
  const heading = company ? `${title}, ${company}` : title

  return (
    <section className="rounded-box border-hairline border-border bg-surface p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <h2 className="text-[13px] font-medium leading-snug text-teal-ink">
          Fit analysis — {heading}
        </h2>
        <span className="flex-shrink-0 rounded-full bg-amber px-2.5 py-[3px] text-[12px] font-medium text-amber-ink">
          {analysis.fit_score} / 100
        </span>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="flex-1">
          <div className="mb-1.5 text-[10px] font-medium tracking-[0.8px] text-text-muted">
            STRENGTHS
          </div>
          {analysis.strengths.length ? (
            <div className="flex flex-wrap gap-1">
              {analysis.strengths.map((strength) => (
                <span
                  key={strength}
                  className="rounded-pill bg-teal-light px-2 py-[3px] text-[11px] text-teal-ink"
                >
                  {strength}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-text-faint">None identified.</p>
          )}
        </div>

        <div className="flex-1">
          <div className="mb-1.5 text-[10px] font-medium tracking-[0.8px] text-text-muted">
            GAPS
          </div>
          {analysis.gaps.length ? (
            <div className="flex flex-wrap gap-1">
              {analysis.gaps.map((gap) => (
                <span
                  key={gap}
                  className="rounded-pill bg-coral-light px-2 py-[3px] text-[11px] text-coral-ink"
                >
                  {gap}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-text-faint">None identified.</p>
          )}
        </div>
      </div>

      {analysis.verdict && (
        <p className="mt-3 border-t border-border pt-3 text-[13px] leading-relaxed text-text-secondary">
          {analysis.verdict}
        </p>
      )}

      {(skills.length > 0 || narrative) && (
        <div className="mt-3 border-t border-border pt-3">
          <button
            type="button"
            onClick={() => setShowSkills((open) => !open)}
            aria-expanded={showSkills}
            className="flex items-center gap-1.5 text-[12px] font-medium text-teal-deep hover:underline"
          >
            {showSkills ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
            {showSkills ? 'Hide' : 'Show'} the skill-by-skill breakdown
            {skills.length > 0 && ` (${skills.length})`}
          </button>

          {showSkills && (
            <div className="mt-3 flex flex-col gap-4">
              {skills.length > 0 && (
                // The table is wide by nature; it scrolls inside its own box so
                // the page never scrolls sideways.
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] border-collapse text-left text-[12px]">
                    <thead>
                      <tr className="text-[10px] font-medium uppercase tracking-[0.8px] text-text-muted">
                        <th className="border-b border-border py-2 pr-3 font-medium">
                          Skill
                        </th>
                        <th className="border-b border-border py-2 pr-3 font-medium">
                          Required
                        </th>
                        <th className="border-b border-border py-2 pr-3 font-medium">
                          You have
                        </th>
                        <th className="border-b border-border py-2 pr-3 font-medium">
                          Evidence
                        </th>
                        <th className="border-b border-border py-2 font-medium">
                          Suggestion
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {skills.map((skill) => (
                        <tr key={skill.skill} className="align-top">
                          <td className="border-b border-border py-2 pr-3 font-medium text-text-primary">
                            {skill.skill}
                          </td>
                          <td className="border-b border-border py-2 pr-3">
                            <Mark
                              on={Boolean(skill.required_by_jd)}
                              label="Required by the job description"
                            />
                          </td>
                          <td className="border-b border-border py-2 pr-3">
                            <Mark
                              on={Boolean(skill.user_has)}
                              label="Present in your profile"
                            />
                          </td>
                          <td className="border-b border-border py-2 pr-3 text-text-secondary">
                            {skill.evidence || skill.gap_reasoning || '—'}
                          </td>
                          <td className="border-b border-border py-2 text-text-secondary">
                            {skill.suggestion || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {narrative && (
                <div className="md-body text-[13px] leading-relaxed text-text-secondary">
                  <ReactMarkdown>{narrative}</ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {onRerun && (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={onRerun}
            disabled={isRerunning}
            className="flex items-center gap-1.5 text-[12px] text-text-muted hover:text-teal-deep disabled:opacity-60"
          >
            {isRerunning ? <Spinner size={13} /> : <RefreshCw size={13} />}
            {isRerunning ? 'Re-running...' : 'Re-run analysis'}
          </button>
          <span className="text-[11px] text-text-faint">
            Replaces the saved result.
          </span>
        </div>
      )}
    </section>
  )
}
