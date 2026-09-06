import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
} from 'lucide-react'
import TopBar from '../common/TopBar'
import ConfirmModal from '../common/ConfirmModal'
import Spinner from '../common/Spinner'
import useAuth from '../../hooks/useAuth'
import { applyProfileImport } from '../../services/profile'
import { useProfileStore } from '../../store/profileStore'
import { pushToast } from '../../store/toastStore'
import { useUiStore } from '../../store/uiStore'
import type {
  ImportChange,
  ImportChangeKind,
  ImportProposal,
  ProfileFieldError,
  ProfileSectionKey,
} from '../../types'

/** Section titles, in the order the profile page renders them. */
const SECTION_LABELS: Record<string, string> = {
  summary: 'Summary',
  work_experience: 'Experience',
  education: 'Education',
  skills: 'Skills',
  certifications: 'Certifications',
  projects: 'Projects',
  achievements: 'Achievements',
  publications: 'Publications',
}

const SECTION_ORDER = Object.keys(SECTION_LABELS)

/** A section name from a newer backend still gets a readable heading. */
function sectionLabel(section: string): string {
  return SECTION_LABELS[section] ?? humanize(section)
}

/** `credential_url` -> `Credential url`. Used for the changed-field lists. */
function humanize(field: string): string {
  const spaced = field.replace(/_/g, ' ').replace(/\./g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

interface SectionGroup {
  section: string
  added: ImportChange[]
  updated: ImportChange[]
  removed: ImportChange[]
  unchanged: ImportChange[]
}

/** Groups the flat change list by section, in profile-page order. */
function groupChanges(changes: ImportChange[]): SectionGroup[] {
  const bySection = new Map<string, SectionGroup>()
  for (const change of changes) {
    let group = bySection.get(change.section)
    if (!group) {
      group = {
        section: change.section,
        added: [],
        updated: [],
        removed: [],
        unchanged: [],
      }
      bySection.set(change.section, group)
    }
    if (change.kind === 'added') group.added.push(change)
    else if (change.kind === 'updated') group.updated.push(change)
    else if (change.kind === 'removed') group.removed.push(change)
    else group.unchanged.push(change)
  }
  return [...bySection.values()].sort((a, b) => {
    const left = SECTION_ORDER.indexOf(a.section)
    const right = SECTION_ORDER.indexOf(b.section)
    // Anything unknown sorts after everything known, rather than to the top.
    return (
      (left === -1 ? SECTION_ORDER.length : left) -
      (right === -1 ? SECTION_ORDER.length : right)
    )
  })
}

/** How many entries in this section the user would actually be changing. */
function changedCount(group: SectionGroup): number {
  return group.added.length + group.updated.length + group.removed.length
}

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

function SummaryTile({
  label,
  count,
  tone,
}: {
  label: string
  count: number
  tone: 'teal' | 'amber' | 'neutral'
}) {
  const tones = {
    teal: 'border-teal-soft bg-teal-light text-teal-ink',
    amber: 'border-amber/30 bg-amber-light text-amber-ink',
    neutral: 'border-border bg-surface text-text-secondary',
  } as const

  return (
    <div className={`flex-1 rounded-box border px-3.5 py-3 ${tones[tone]}`}>
      <p className="text-[22px] font-medium leading-none tabular-nums">{count}</p>
      <p className="mt-1.5 text-[12px] font-medium uppercase tracking-[0.6px]">
        {label}
      </p>
    </div>
  )
}

/** How each change kind is tinted, labelled, and pilled. */
const ROW_TONES: Record<ImportChangeKind, { row: string; pill: string; label: string }> = {
  added: {
    row: 'border-teal-soft bg-teal-light',
    pill: 'bg-teal-deep text-white',
    label: 'New',
  },
  updated: {
    row: 'border-amber/30 bg-amber-light',
    pill: 'bg-amber text-white',
    label: 'Updated',
  },
  removed: {
    row: 'border-coral/30 bg-coral-light',
    pill: 'bg-coral text-white',
    label: 'Removed',
  },
  unchanged: {
    row: 'border-border bg-surface',
    pill: 'bg-border-input text-text-secondary',
    label: 'Same',
  },
}

/** One proposed entry: a tinted row with its label, and what changed on it. */
function ChangeRow({ change }: { change: ImportChange }) {
  const isUpdated = change.kind === 'updated'
  const tone = ROW_TONES[change.kind] ?? ROW_TONES.unchanged

  return (
    <li className={`rounded-box border px-3 py-2.5 ${tone.row}`}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span
          className={`rounded-pill px-2 py-[2px] text-[10px] font-medium uppercase tracking-[0.5px] ${tone.pill}`}
        >
          {tone.label}
        </span>
        <span className="min-w-0 break-words text-[13px] text-text-primary">
          {change.label || 'Untitled entry'}
        </span>
      </div>
      {isUpdated && (change.fields?.length ?? 0) > 0 && (
        <p className="mt-1 text-[12px] leading-relaxed text-amber-ink">
          Changes: {(change.fields ?? []).map(humanize).join(', ')}
        </p>
      )}
    </li>
  )
}

function SectionCard({
  group,
  checked,
  onToggle,
}: {
  group: SectionGroup
  checked: boolean
  onToggle: (next: boolean) => void
}) {
  const [showUnchanged, setShowUnchanged] = useState(false)
  const changed = changedCount(group)

  return (
    <section className="rounded-card border border-border bg-card p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-serif text-[17px] font-medium text-teal-ink">
            {sectionLabel(group.section)}
          </h2>
          <p className="mt-0.5 text-[12px] text-text-muted">
            {changed === 0
              ? 'Nothing new in this section'
              : [
                  group.added.length ? `${group.added.length} new` : null,
                  group.updated.length ? `${group.updated.length} updated` : null,
                  group.removed.length ? `${group.removed.length} removed` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
          </p>
        </div>
        <label className="flex flex-shrink-0 cursor-pointer items-center gap-2 text-[13px] font-medium text-text-primary">
          <input
            type="checkbox"
            checked={checked}
            onChange={(event) => onToggle(event.target.checked)}
            className="h-4 w-4 accent-[#1D9E75]"
          />
          Apply this section
        </label>
      </div>

      {changed > 0 && (
        <ul className="flex flex-col gap-2">
          {group.added.map((change, index) => (
            <ChangeRow key={`added-${index}`} change={change} />
          ))}
          {group.updated.map((change, index) => (
            <ChangeRow key={`updated-${index}`} change={change} />
          ))}
          {group.removed.map((change, index) => (
            <ChangeRow key={`removed-${index}`} change={change} />
          ))}
        </ul>
      )}

      {group.unchanged.length > 0 && (
        <div className={changed > 0 ? 'mt-3' : ''}>
          <button
            type="button"
            onClick={() => setShowUnchanged((current) => !current)}
            aria-expanded={showUnchanged}
            className="flex min-h-[36px] items-center gap-1 text-[12px] font-medium text-teal-deep underline-offset-2 hover:underline"
          >
            {showUnchanged ? (
              <ChevronDown size={13} />
            ) : (
              <ChevronRight size={13} />
            )}
            {showUnchanged ? 'Hide' : 'Show'} unchanged ({group.unchanged.length})
          </button>
          {showUnchanged && (
            <ul className="mt-2 flex flex-col gap-2">
              {group.unchanged.map((change, index) => (
                <ChangeRow key={`unchanged-${index}`} change={change} />
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Applying a section replaces it wholesale, so an unchanged entry the
          file also describes is still written back exactly as it stands. */}
      {checked && group.unchanged.length > 0 && changed === 0 && (
        <p className="mt-3 text-[12px] leading-relaxed text-text-muted">
          This section is identical to what you already have. Applying it changes
          nothing.
        </p>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Screen                                                              */
/* ------------------------------------------------------------------ */

function Header({ source }: { source: ImportProposal['source'] }) {
  const read = source.sheets.filter((sheet) => !sheet.skipped_reason)
  const skipped = source.sheets.filter((sheet) => sheet.skipped_reason)

  return (
    <section className="rounded-card border border-border bg-card p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-box bg-teal-light">
          <FileSpreadsheet size={17} className="text-teal-deep" />
        </span>
        <div className="min-w-0">
          <p className="break-words text-[14px] font-medium text-text-primary">
            {source.filename ?? 'Uploaded file'}
          </p>
          <p className="mt-0.5 text-[12px] leading-relaxed text-text-muted">
            {read.length === 0
              ? 'Read as a single document.'
              : `Read ${read.length} ${read.length === 1 ? 'sheet' : 'sheets'}: ${read
                  .map(
                    (sheet) =>
                      `${sheet.name} (${sheet.rows} ${
                        sheet.rows === 1 ? 'row' : 'rows'
                      })`,
                  )
                  .join(', ')}`}
          </p>
        </div>
      </div>

      {skipped.length > 0 && (
        <div className="mt-3 flex items-start gap-2 rounded-box border border-amber/30 bg-amber-light px-3 py-2.5">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-amber-ink" />
          <div className="min-w-0 text-[12px] leading-relaxed text-amber-ink">
            {skipped.map((sheet) => (
              <p key={sheet.name}>
                <span className="font-medium">{sheet.name}</span> was skipped —{' '}
                {sheet.skipped_reason}
              </p>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function NothingFound({ filename }: { filename: string | null }) {
  return (
    <div className="rounded-card border border-border bg-card px-5 py-12 text-center sm:px-6 sm:py-14">
      <h2 className="font-serif text-[20px] font-medium text-teal-ink">
        Nothing new found in this file
      </h2>
      <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-secondary">
        Everything {filename ? `in ${filename}` : 'in that file'} either matches
        what your profile already says or carried nothing we could read. Nothing
        has been changed.
      </p>
      <Link
        to="/profile"
        className="mt-6 inline-flex min-h-[44px] items-center rounded-btn bg-coral px-5 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95"
      >
        Back to your profile
      </Link>
    </div>
  )
}

/**
 * The review step between reading a supplementary file and saving anything
 * from it.
 *
 * The proposal is a whole `parsed_json` the server would write, and the only
 * decision offered here is which *sections* to accept — deliberately not which
 * entries. A per-entry picker would have to rebuild the merged section on the
 * client and re-run the backend's own merge rules to do it honestly, and the
 * profile editor one screen away already edits every field properly. So: pick
 * sections, apply, then edit.
 */
export default function ImportReview() {
  const navigate = useNavigate()
  const proposal = useProfileStore((state) => state.importProposal)
  const setImportProposal = useProfileStore((state) => state.setImportProposal)
  const setProfile = useProfileStore((state) => state.setProfile)
  const fetchGaps = useProfileStore((state) => state.fetchGaps)
  const resetDismissals = useProfileStore((state) => state.resetDismissals)
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)
  const { setHasProfile } = useAuth()

  const groups = useMemo(
    () => (proposal ? groupChanges(proposal.changes) : []),
    [proposal],
  )

  // The server's own totals, not a sum over `groups`: a change kind a newer
  // backend introduces is still counted honestly in the tiles.
  const tally = proposal?.summary ?? {
    added: 0,
    updated: 0,
    unchanged: 0,
    removed: 0,
    sections: {},
  }

  // Default on for a section with something to apply, off for one that would
  // rewrite what is already there with the same values.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [isApplying, setIsApplying] = useState(false)
  const [errors, setErrors] = useState<ProfileFieldError[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)

  useEffect(() => {
    setSelected(
      new Set(
        groups
          .filter((group) => changedCount(group) > 0)
          .map((group) => group.section),
      ),
    )
  }, [groups])

  // A refresh drops the proposal (it is never persisted), so there is nothing
  // left to review — say so and go back rather than showing an empty screen.
  useEffect(() => {
    if (proposal) return
    pushToast('That import is no longer available. Upload the file again.', 'info')
    navigate('/profile', { replace: true })
  }, [proposal, navigate])

  if (!proposal) return null

  const hasChanges = tally.added + tally.updated + tally.removed > 0

  function toggleSection(section: string, next: boolean) {
    setSelected((current) => {
      const updated = new Set(current)
      if (next) updated.add(section)
      else updated.delete(section)
      return updated
    })
  }

  function discard() {
    setImportProposal(null)
    pushToast('Import discarded. Nothing was changed.', 'info')
    navigate('/profile', { replace: true })
  }

  async function apply() {
    if (!proposal || isApplying || selected.size === 0) return

    setIsApplying(true)
    setErrors([])
    setErrorMessage(null)

    const sections = SECTION_ORDER.filter((section) =>
      selected.has(section),
    ) as ProfileSectionKey[]
    // A section only this backend knows about is still applied, after the ones
    // this build knows the order of.
    const extra = [...selected].filter(
      (section) => !SECTION_ORDER.includes(section),
    ) as ProfileSectionKey[]

    const result = await applyProfileImport(
      proposal.proposal,
      [...sections, ...extra],
      proposal.source.filename,
      proposal.document_text,
    )
    setIsApplying(false)

    if (!result.ok) {
      setErrorMessage(result.message)
      setErrors(result.errors)
      return
    }

    setProfile(result.profile)
    setHasProfile(true)
    // The profile just changed shape: every nudge dismissed against the old one
    // is spent, exactly as after a fresh resume upload.
    resetDismissals()
    setImportProposal(null)
    void fetchGaps()
    pushToast(
      proposal.source.filename
        ? `Profile updated from ${proposal.source.filename}`
        : 'Profile updated from your file',
      'success',
    )
    navigate('/profile', { replace: true })
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar
        title="Review imported changes"
        subtitle="Nothing is saved until you apply"
        onMenu={toggleSidebar}
      />

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 md:px-8">
        <div className="mx-auto flex w-full max-w-[900px] flex-col gap-4">
          {errorMessage && (
            <div
              role="alert"
              className="rounded-card border border-coral/30 bg-coral-light px-4 py-3.5"
            >
              <p className="text-[13px] leading-relaxed text-coral-ink">
                {errorMessage}
              </p>
              {errors.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] leading-relaxed text-coral-ink">
                  {errors.map((error, index) => (
                    <li key={index}>
                      {sectionLabel(error.section)}
                      {error.index === null ? '' : ` (entry ${error.index + 1})`}:{' '}
                      {error.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <Header source={proposal.source} />

          {!hasChanges ? (
            <NothingFound filename={proposal.source.filename} />
          ) : (
            <>
              <div className="flex gap-2 sm:gap-3">
                <SummaryTile label="Added" count={tally.added} tone="teal" />
                <SummaryTile label="Updated" count={tally.updated} tone="amber" />
                <SummaryTile
                  label="Unchanged"
                  count={tally.unchanged}
                  tone="neutral"
                />
              </div>

              <p className="text-[12px] leading-relaxed text-text-muted">
                No editing here — pick the sections to accept.{' '}
                <Link
                  to="/profile"
                  className="font-medium text-teal-deep underline underline-offset-2 hover:text-teal-ink"
                >
                  You can edit everything after applying
                </Link>
                .
              </p>

              {groups.map((group) => (
                <SectionCard
                  key={group.section}
                  group={group}
                  checked={selected.has(group.section)}
                  onToggle={(next) => toggleSection(group.section, next)}
                />
              ))}

              {/* Sticky rather than at the end of a long list: the decision
                  this screen exists for should not require scrolling past
                  every section to reach. */}
              <div className="sticky bottom-0 -mx-4 mt-1 flex items-center justify-end gap-2 border-t border-border bg-bg px-4 py-3 sm:mx-0 sm:rounded-card sm:border">
                <button
                  type="button"
                  onClick={() => setConfirmingDiscard(true)}
                  disabled={isApplying}
                  className="flex min-h-[44px] items-center justify-center rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-secondary transition-colors hover:border-teal-soft hover:text-teal-ink disabled:opacity-50"
                >
                  Discard import
                </button>
                <button
                  type="button"
                  onClick={() => void apply()}
                  disabled={isApplying || selected.size === 0}
                  className="flex min-h-[44px] items-center justify-center gap-2 rounded-btn bg-coral px-5 py-2 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {isApplying && <Spinner size={14} className="text-white" />}
                  {isApplying
                    ? 'Applying...'
                    : `Apply ${selected.size} ${
                        selected.size === 1 ? 'section' : 'sections'
                      }`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <ConfirmModal
        open={confirmingDiscard}
        title="Discard this import?"
        description="The file will not be read again and nothing in your profile changes. You can always upload it again later."
        confirmLabel="Discard"
        cancelLabel="Keep reviewing"
        onCancel={() => setConfirmingDiscard(false)}
        onConfirm={() => {
          setConfirmingDiscard(false)
          discard()
        }}
      />
    </div>
  )
}
