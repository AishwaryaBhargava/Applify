import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, FileCheck2, Plus, ScanSearch } from 'lucide-react'
import Spinner from '../common/Spinner'
import { useProfileStore } from '../../store/profileStore'
import { pushToast } from '../../store/toastStore'
import type { KeywordMatch, KeywordMatchItem } from '../../types'

interface KeywordMatchPanelProps {
  match: KeywordMatch | null
  isRunning?: boolean
  /** `force` re-extracts the keyword list; without it only matching re-runs. */
  onRun: (force?: boolean) => void
  error?: string | null
  /** 409 — there is no profile to match the posting against. */
  needsResume?: boolean
}

/** The two categories a keyword can be added to the profile's skills as. */
const ADDABLE = new Set(['skill', 'tool'])

/** Human labels for the category shown behind a chip's tooltip. */
const CATEGORY_LABELS: Record<KeywordMatchItem['category'], string> = {
  skill: 'Skill',
  tool: 'Tool',
  qualification: 'Qualification',
  responsibility: 'Responsibility',
  soft_skill: 'Soft skill',
  domain: 'Domain',
}

const RING_SIZE = 84
const RING_STROKE = 8
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS

/**
 * The score, drawn as a ring rather than a bar.
 *
 * Amber, like the fit pill on the analysis card — the two numbers sit inches
 * apart and answer the same question from different angles, so they read as
 * one family rather than two unrelated scores.
 */
function MatchRing({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)))
  const filled = (clamped / 100) * RING_CIRCUMFERENCE

  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: RING_SIZE, height: RING_SIZE }}
      role="img"
      aria-label={`${clamped} percent keyword match`}
    >
      <svg
        width={RING_SIZE}
        height={RING_SIZE}
        viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
        aria-hidden="true"
        // Rotated so the fill starts at twelve o'clock instead of three.
        className="-rotate-90"
      >
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke="#F1EFE8"
          strokeWidth={RING_STROKE}
        />
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          fill="none"
          stroke="#EF9F27"
          strokeWidth={RING_STROKE}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${RING_CIRCUMFERENCE}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-[22px] font-medium leading-none text-teal-ink">
          {clamped}
        </span>
        <span className="mt-0.5 text-[10px] text-text-muted">%</span>
      </div>
    </div>
  )
}

/** Placeholder in the shape of the result, shown while the match runs. */
function KeywordSkeleton() {
  return (
    <div
      role="status"
      aria-label="Matching the posting against your profile"
      className="animate-pulse"
    >
      <div className="flex items-center gap-4">
        <div
          className="flex-shrink-0 rounded-full bg-surface-warm"
          style={{ width: RING_SIZE, height: RING_SIZE }}
        />
        <div className="min-w-0 flex-1">
          <div className="h-2.5 w-40 rounded-badge bg-surface-warm" />
          <div className="mt-2 h-2.5 w-28 rounded-badge bg-surface-warm" />
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        {['missing', 'matched'].map((column) => (
          <div key={column} className="flex-1">
            <div className="mb-2 h-2 w-16 rounded-badge bg-surface-warm" />
            <div className="flex flex-wrap gap-1">
              <div className="h-5 w-20 rounded-pill bg-surface-warm" />
              <div className="h-5 w-24 rounded-pill bg-surface-warm" />
              <div className="h-5 w-16 rounded-pill bg-surface-warm" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * The ATS keyword match: what the posting asks for in its own words, and
 * whether the profile — and the tailored resume, once there is one — says it
 * back.
 *
 * A deliberately different question from the fit analysis above it. The
 * analysis is a judgement about the candidate; this is a literal string match
 * of the kind an applicant tracking system performs before a human ever reads
 * the application, which is why a missing keyword here is worth acting on even
 * when the analysis is happy.
 */
export default function KeywordMatchPanel({
  match,
  isRunning = false,
  onRun,
  error,
  needsResume = false,
}: KeywordMatchPanelProps) {
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [addingKeyword, setAddingKeyword] = useState<string | null>(null)
  const fetchProfile = useProfileStore((state) => state.fetchProfile)
  const updateSection = useProfileStore((state) => state.updateSection)

  const { missing, matched, inResumeTotal, inResumeMatched } = useMemo(() => {
    const keywords = match?.keywords ?? []
    // Required first inside each column: a missing "must have Kubernetes" is
    // not the same size of problem as a missing "nice to have Terraform".
    const byImportance = (a: KeywordMatchItem, b: KeywordMatchItem) =>
      a.importance === b.importance ? 0 : a.importance === 'required' ? -1 : 1

    const checkedAgainstResume = keywords.filter(
      (keyword) => keyword.in_resume !== null,
    )

    return {
      missing: keywords.filter((k) => !k.in_profile).sort(byImportance),
      matched: keywords.filter((k) => k.in_profile).sort(byImportance),
      inResumeTotal: checkedAgainstResume.length,
      inResumeMatched: checkedAgainstResume.filter((k) => k.in_resume).length,
    }
  }, [match])

  /**
   * Adds one keyword to the profile's skills, then re-runs the match.
   *
   * Not forced: the keyword list is unchanged — only the profile it is matched
   * against moved — so re-extracting the posting would spend a model call to
   * produce the list we already have.
   */
  const addToSkills = useCallback(
    async (keyword: string) => {
      setAddingKeyword(keyword)
      // The chat page never loads the profile for itself — it is persisted from
      // the last profile visit, and on a fresh tab it may not be there at all.
      // Writing `skills` from an empty local copy would erase every skill the
      // section holds, because PATCH replaces a section wholesale.
      if (!useProfileStore.getState().profile) await fetchProfile()
      const current = useProfileStore.getState().profile
      if (!current) {
        setAddingKeyword(null)
        pushToast('Upload your resume before adding skills', 'error')
        return
      }

      const skills = current.parsed_json.skills ?? []
      if (
        skills.some(
          (skill) => skill.toLowerCase() === keyword.trim().toLowerCase(),
        )
      ) {
        // Already there and the match still says it is missing: adding a second
        // copy would not change the answer, so say so instead of writing one.
        setAddingKeyword(null)
        pushToast(`"${keyword}" is already in your skills`, 'info')
        return
      }

      const result = await updateSection('skills', [...skills, keyword.trim()])
      setAddingKeyword(null)

      if (result.ok) {
        pushToast(`Added "${keyword}" to your skills`, 'success')
        onRun(false)
      } else {
        pushToast(result.message, 'error')
      }
    },
    [fetchProfile, onRun, updateSection],
  )

  const header = (
    <header className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="flex items-center gap-1.5 text-[13px] font-medium leading-snug text-teal-ink">
          <ScanSearch size={14} className="flex-shrink-0 text-text-muted" />
          ATS keyword match
        </h2>
      </div>
      {match && (
        <button
          type="button"
          onClick={() => onRun(true)}
          disabled={isRunning}
          className="flex-shrink-0 text-[12px] text-text-muted underline-offset-2 hover:text-teal-deep hover:underline disabled:opacity-60"
        >
          Re-extract keywords
        </button>
      )}
    </header>
  )

  /* ---------------------------------------------------------------- */
  /* Not run yet                                                       */
  /* ---------------------------------------------------------------- */

  if (!match && !isRunning) {
    return (
      <section className="rounded-box border-hairline border-border bg-surface p-3.5 sm:p-4">
        {header}
        <p className="text-[13px] leading-relaxed text-text-secondary">
          Most applications are read by software before a person sees them.
          Applify pulls the exact words this posting screens on and checks them
          against your profile.
        </p>

        {needsResume ? (
          <div className="mt-3 flex items-start gap-2.5 rounded-box border border-amber/30 bg-amber-light px-3.5 py-3 text-[13px] leading-relaxed text-amber-ink">
            <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
            <div>
              <p className="font-medium">{error}</p>
              <p className="mt-1">
                There is nothing to match the posting against yet.{' '}
                <Link
                  to="/onboarding"
                  className="font-medium underline underline-offset-2"
                >
                  Upload your resume
                </Link>
                , then run it again.
              </p>
            </div>
          </div>
        ) : (
          error && (
            <div className="mt-3 flex items-start gap-2.5 rounded-box bg-coral-light px-3.5 py-3 text-[13px] leading-relaxed text-coral-ink">
              <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
              <p>{error}</p>
            </div>
          )
        )}

        <button
          type="button"
          onClick={() => onRun(false)}
          className="mt-3 flex min-h-[42px] items-center gap-2 rounded-btn bg-teal-deep px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
        >
          <ScanSearch size={15} />
          Run keyword match
        </button>
      </section>
    )
  }

  /* ---------------------------------------------------------------- */
  /* Running, with nothing to keep on screen                           */
  /* ---------------------------------------------------------------- */

  if (!match) {
    return (
      <section className="rounded-box border-hairline border-border bg-surface p-3.5 sm:p-4">
        {header}
        <KeywordSkeleton />
      </section>
    )
  }

  /* ---------------------------------------------------------------- */
  /* Result                                                            */
  /* ---------------------------------------------------------------- */

  return (
    <section className="rounded-box border-hairline border-border bg-surface p-3.5 sm:p-4">
      {header}

      <div className="flex items-center gap-4">
        <MatchRing percent={match.match_percent} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-relaxed text-text-secondary">
            <span className="font-medium text-text-primary">
              {match.required_matched} of {match.required_total}
            </span>{' '}
            required,{' '}
            <span className="font-medium text-text-primary">
              {match.preferred_matched} of {match.preferred_total}
            </span>{' '}
            preferred keywords found in your profile.
          </p>

          {inResumeTotal > 0 && (
            <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-text-muted">
              <FileCheck2 size={13} className="flex-shrink-0 text-teal-medium" />
              In your tailored resume:{' '}
              <span className="font-medium text-text-secondary">
                {inResumeMatched} of {inResumeTotal}
              </span>
            </p>
          )}

          {isRunning && (
            <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-text-muted">
              <Spinner size={12} />
              Re-checking...
            </p>
          )}
        </div>
      </div>

      {error && !needsResume && (
        <div className="mt-3 flex items-start gap-2.5 rounded-box bg-coral-light px-3.5 py-2.5 text-[12px] leading-relaxed text-coral-ink">
          <AlertCircle size={14} className="mt-[2px] flex-shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:gap-5">
        {/* Missing ------------------------------------------------- */}
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 text-[11px] font-medium tracking-[0.8px] text-text-muted sm:text-[10px]">
            MISSING ({missing.length})
          </div>
          {missing.length === 0 ? (
            <p className="text-[12px] text-text-faint">
              Nothing this posting asks for is absent from your profile.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1">
              {missing.map((keyword) => {
                const required = keyword.importance === 'required'
                const addable = ADDABLE.has(keyword.category)
                const busy = addingKeyword === keyword.keyword

                return (
                  <li key={keyword.keyword}>
                    <span
                      title={`${CATEGORY_LABELS[keyword.category]} — ${required ? 'required' : 'preferred'}`}
                      className={`inline-flex items-center gap-1 rounded-pill py-[3px] pl-2 text-[12px] leading-snug sm:text-[11px] ${
                        addable ? 'pr-1' : 'pr-2'
                      } ${
                        required
                          ? 'bg-coral-light text-coral-ink'
                          : 'bg-surface-warm text-text-secondary'
                      }`}
                    >
                      {keyword.keyword}
                      {addable && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void addToSkills(keyword.keyword)}
                          aria-label={`Add ${keyword.keyword} to your skills`}
                          title="Add to your profile skills"
                          className="flex items-center gap-0.5 rounded-badge px-1 py-[1px] text-[11px] font-medium opacity-80 hover:bg-card hover:opacity-100 disabled:opacity-50 sm:text-[10px]"
                        >
                          {busy ? <Spinner size={10} /> : <Plus size={11} />}
                          Add
                        </button>
                      )}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Matched ------------------------------------------------- */}
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 text-[11px] font-medium tracking-[0.8px] text-text-muted sm:text-[10px]">
            MATCHED ({matched.length})
          </div>
          {matched.length === 0 ? (
            <p className="text-[12px] text-text-faint">
              None of this posting&apos;s keywords are in your profile yet.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1">
              {matched.map((keyword) => {
                const open = openEvidence === keyword.keyword
                const evidence = keyword.evidence?.trim()

                return (
                  <li key={keyword.keyword}>
                    {/*
                      A button, not a tooltip: there is no hover on a phone, and
                      the evidence snippet is the part that makes the match
                      believable. The title attribute keeps the mouse path.
                    */}
                    <button
                      type="button"
                      onClick={() =>
                        setOpenEvidence(open ? null : keyword.keyword)
                      }
                      aria-expanded={evidence ? open : undefined}
                      title={evidence || 'Found in your profile'}
                      className="inline-flex items-center gap-1 rounded-pill bg-teal-light px-2 py-[3px] text-[12px] leading-snug text-teal-ink hover:bg-teal-soft/50 sm:text-[11px]"
                    >
                      {keyword.keyword}
                      {keyword.in_resume === true && (
                        <FileCheck2
                          size={11}
                          aria-label="also in your tailored resume"
                          className="flex-shrink-0 text-teal-deep"
                        />
                      )}
                    </button>
                    {open && (
                      <div className="mt-1 rounded-input border border-border bg-card px-2 py-1.5 text-[12px] leading-relaxed text-text-secondary sm:text-[11px]">
                        <p>{evidence || 'Found in your profile.'}</p>
                        {/* Why a different spelling counted — the question the
                            user asks the moment a match looks too generous. */}
                        {keyword.aliases && keyword.aliases.length > 0 && (
                          <p className="mt-1 text-text-faint">
                            Also counted: {keyword.aliases.join(', ')}
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {match.missing_required.length > 0 && (
        <p className="mt-3 border-t border-border pt-3 text-[12px] leading-relaxed text-text-secondary">
          <span className="font-medium text-coral-ink">
            {match.missing_required.length} required keyword
            {match.missing_required.length === 1 ? '' : 's'}
          </span>{' '}
          {match.missing_required.length === 1 ? 'is' : 'are'} missing. Adding
          the ones you genuinely have is the cheapest thing you can do for this
          application.
        </p>
      )}
    </section>
  )
}
