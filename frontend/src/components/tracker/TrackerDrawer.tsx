import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, MessageSquare, X } from 'lucide-react'
import ConfirmModal from '../common/ConfirmModal'
import Spinner from '../common/Spinner'
import {
  PRIORITY_LABELS,
  PRIORITY_ORDER,
  STATUS_LABELS,
  STATUS_ORDER,
} from './statuses'
import { entryTitle, toDateInputValue } from '../../lib/format'
import { validateJobUrl } from '../../lib/validation'
import { TRACKER_SOURCES } from '../../types'
import type {
  AnalysisType,
  TrackerEntry,
  TrackerEntryPatch,
  TrackerPriority,
  TrackerStatus,
} from '../../types'

interface TrackerDrawerProps {
  entry: TrackerEntry | null
  open: boolean
  onClose: () => void
  /** Resolves to true when the PATCH landed and the drawer may close. */
  onSave: (chatId: string, patch: TrackerEntryPatch) => Promise<boolean>
  isSaving?: boolean
}

const ANALYSIS_LABELS: Record<AnalysisType, string> = {
  quick: 'Quick snapshot',
  detailed: 'Detailed breakdown',
}

/** Every editable field, as the form holds it: strings all the way down. */
interface DraftFields {
  status: TrackerStatus
  priority: string
  applied_at: string
  job_url: string
  location: string
  salary: string
  source: string
  next_action: string
  next_action_date: string
  notes: string
}

/** An empty input means "not set", which on the wire is null rather than ''. */
function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

/**
 * The date input's `YYYY-MM-DD` as an ISO timestamp.
 *
 * Anchored at **local noon** rather than local midnight. Midnight is within a
 * day's travel of the date line in either direction, so a user in Auckland or
 * Los Angeles would watch the date they typed come back one day off; noon has
 * twelve hours of slack on both sides and survives every real timezone.
 */
function dateInputToIso(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!match) return null
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    12,
  )
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function draftFrom(entry: TrackerEntry | null): DraftFields {
  return {
    status: entry?.status ?? 'not_applied',
    priority: entry?.priority ?? '',
    applied_at: toDateInputValue(entry?.applied_at),
    job_url: entry?.job_url ?? '',
    location: entry?.location ?? '',
    salary: entry?.salary ?? '',
    source: entry?.source ?? '',
    next_action: entry?.next_action ?? '',
    next_action_date: toDateInputValue(entry?.next_action_date),
    notes: entry?.notes ?? '',
  }
}

const FIELD_CLASS =
  'min-h-[44px] w-full rounded-input border border-border-input bg-card px-3 py-2 text-[16px] outline-none focus:border-teal-deep sm:min-h-0 sm:text-[13px]'

const LABEL_CLASS = 'text-[12px] font-medium text-text-secondary'

function Field({
  label,
  children,
  className = '',
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <label className={`flex flex-col gap-1.5 ${className}`}>
      <span className={LABEL_CLASS}>{label}</span>
      {children}
    </label>
  )
}

/**
 * Everything about one application, editable in place.
 *
 * A drawer rather than a page because the tracker's job is comparison — you
 * open a row to update it and go straight back to the list, and a route
 * change would lose the scroll position and the filter you were reading it
 * through. Below 640px it becomes a full-height sheet: a 400px panel over a
 * 375px phone is a modal that pretends to be a drawer.
 *
 * Saving is explicit, with the same dirty-state contract as the profile
 * editor: nothing is written until Save, Discard asks before it throws work
 * away, and closing with unsaved changes asks too rather than quietly
 * dropping them.
 */
export default function TrackerDrawer({
  entry,
  open,
  onClose,
  onSave,
  isSaving = false,
}: TrackerDrawerProps) {
  const [draft, setDraft] = useState<DraftFields>(() => draftFrom(entry))
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)

  const initial = useMemo(() => draftFrom(entry), [entry])

  // Reloading the draft when the row behind it changes is what makes clicking
  // straight from one row to another work; it also adopts the server's copy
  // after a save, so the drawer stops being dirty the moment the PATCH lands.
  useEffect(() => {
    setDraft(initial)
    setConfirmingDiscard(false)
  }, [initial])

  const isDirty = useMemo(
    () =>
      (Object.keys(initial) as (keyof DraftFields)[]).some(
        (key) => draft[key] !== initial[key],
      ),
    [draft, initial],
  )

  // Checked here rather than only server-side: the backend rejects a non-http
  // URL with a 422, and a toast after the save is a worse way to learn it than
  // a line under the field that was wrong.
  const jobUrlError = validateJobUrl(draft.job_url)

  const requestClose = useCallback(() => {
    if (isDirty) setConfirmingDiscard(true)
    else onClose()
  }, [isDirty, onClose])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') requestClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, requestClose])

  if (!open || !entry) return null

  const set = <K extends keyof DraftFields>(key: K, value: DraftFields[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  /** Only what actually moved, so a save never rewrites an untouched field. */
  function buildPatch(): TrackerEntryPatch {
    const patch: TrackerEntryPatch = {}
    if (draft.status !== initial.status) patch.status = draft.status
    if (draft.priority !== initial.priority) {
      patch.priority = (draft.priority || null) as TrackerPriority | null
    }
    if (draft.applied_at !== initial.applied_at) {
      patch.applied_at = dateInputToIso(draft.applied_at)
    }
    if (draft.job_url !== initial.job_url) patch.job_url = orNull(draft.job_url)
    if (draft.location !== initial.location) {
      patch.location = orNull(draft.location)
    }
    if (draft.salary !== initial.salary) patch.salary = orNull(draft.salary)
    if (draft.source !== initial.source) patch.source = orNull(draft.source)
    if (draft.next_action !== initial.next_action) {
      patch.next_action = orNull(draft.next_action)
    }
    if (draft.next_action_date !== initial.next_action_date) {
      // A date-only field goes across as the date, not as a moment in time.
      patch.next_action_date = orNull(draft.next_action_date)
    }
    if (draft.notes !== initial.notes) patch.notes = orNull(draft.notes)
    return patch
  }

  async function save() {
    if (!entry || isSaving || jobUrlError) return
    const patch = buildPatch()
    if (Object.keys(patch).length === 0) {
      onClose()
      return
    }
    if (await onSave(entry.chat_id, patch)) onClose()
  }

  const title = entryTitle(entry)

  return (
    <>
      {/*
        The scrim is a sibling of the panel rather than its parent: a click on
        the panel would otherwise have to be stopped from bubbling out to the
        close handler, and that is the kind of thing that breaks the first time
        a nested control calls stopPropagation for its own reasons.
      */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        role="presentation"
        onMouseDown={requestClose}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Application details for ${title}`}
        /* Full-height sheet under 640px; a 420px panel from there up. */
        className="fixed inset-0 z-50 flex flex-col bg-card sm:inset-y-0 sm:left-auto sm:right-0 sm:w-[420px] sm:border-l sm:border-border"
      >
        <header className="flex flex-shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 className="break-words font-serif text-lg font-medium leading-snug text-teal-ink">
              {title}
            </h2>
            <p className="mt-0.5 truncate text-[12px] text-text-muted">
              {entry.company ?? 'No company on this chat'}
            </p>
            <Link
              to={`/chat/${entry.chat_id}`}
              className="mt-1.5 inline-flex min-h-[36px] items-center gap-1.5 text-[12px] font-medium text-teal-deep underline-offset-2 hover:underline"
            >
              <MessageSquare size={13} />
              Open the job chat
            </Link>
          </div>
          <button
            type="button"
            onClick={requestClose}
            aria-label="Close details"
            className="-mr-2 -mt-1.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-text-muted hover:bg-surface-warm hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {/* Read-only, because neither is the user's to set: the fit score is
              the analysis's, and the depth is whichever one ran. */}
          <div className="mb-5 flex flex-wrap items-center gap-2">
            {typeof entry.fit_score === 'number' ? (
              <span className="rounded-full bg-amber px-2.5 py-[3px] text-[12px] font-medium text-amber-ink">
                Fit {entry.fit_score} / 100
              </span>
            ) : (
              <span className="rounded-full bg-surface-warm px-2.5 py-[3px] text-[12px] text-text-muted">
                Not analysed yet
              </span>
            )}
            {entry.analysis_type && (
              <span className="rounded-full bg-surface-warm px-2.5 py-[3px] text-[12px] text-text-secondary">
                {ANALYSIS_LABELS[entry.analysis_type]}
              </span>
            )}
            <span
              className={`rounded-full px-2.5 py-[3px] text-[12px] font-medium ${
                entry.resume_type === 'tailored'
                  ? 'bg-teal-light text-teal-ink'
                  : 'bg-surface-warm text-text-secondary'
              }`}
            >
              {entry.resume_type === 'tailored'
                ? 'AI-tailored resume'
                : 'Unaltered resume'}
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Status">
              <select
                value={draft.status}
                onChange={(event) =>
                  set('status', event.target.value as TrackerStatus)
                }
                className={FIELD_CLASS}
              >
                {STATUS_ORDER.map((status) => (
                  <option
                    key={status}
                    value={status}
                    className="bg-card text-text-primary"
                  >
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Priority">
              <select
                value={draft.priority}
                onChange={(event) => set('priority', event.target.value)}
                className={FIELD_CLASS}
              >
                <option value="">Not set</option>
                {PRIORITY_ORDER.map((priority) => (
                  <option key={priority} value={priority}>
                    {PRIORITY_LABELS[priority]}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Applied on" className="sm:col-span-2">
              <input
                type="date"
                value={draft.applied_at}
                onChange={(event) => set('applied_at', event.target.value)}
                className={FIELD_CLASS}
              />
              <span className="text-[11px] text-text-faint">
                Filled in for you the first time you mark this applied.
              </span>
            </Field>

            <Field label="Job URL" className="sm:col-span-2">
              <input
                type="url"
                inputMode="url"
                value={draft.job_url}
                onChange={(event) => set('job_url', event.target.value)}
                placeholder="https://..."
                className={FIELD_CLASS}
              />
              {jobUrlError ? (
                <span className="text-[11px] text-coral-ink">{jobUrlError}</span>
              ) : (
                draft.job_url.trim() && (
                  <a
                    href={draft.job_url.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[12px] font-medium text-teal-deep underline-offset-2 hover:underline"
                  >
                    <ExternalLink size={12} />
                    Open the posting
                  </a>
                )
              )}
            </Field>

            <Field label="Location">
              <input
                value={draft.location}
                onChange={(event) => set('location', event.target.value)}
                placeholder="Remote — UK"
                className={FIELD_CLASS}
              />
            </Field>

            <Field label="Salary">
              <input
                value={draft.salary}
                onChange={(event) => set('salary', event.target.value)}
                placeholder="£70-85k"
                className={FIELD_CLASS}
              />
            </Field>

            <Field label="Source" className="sm:col-span-2">
              <select
                value={draft.source}
                onChange={(event) => set('source', event.target.value)}
                className={FIELD_CLASS}
              >
                <option value="">Not set</option>
                {/* A source stored before this list existed is still shown,
                    rather than silently reset to "Not set" on the next save. */}
                {(TRACKER_SOURCES as readonly string[]).includes(draft.source) ||
                !draft.source ? null : (
                  <option value={draft.source}>{draft.source}</option>
                )}
                {TRACKER_SOURCES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Next action" className="sm:col-span-2">
              <input
                value={draft.next_action}
                onChange={(event) => set('next_action', event.target.value)}
                placeholder="Follow up with the recruiter"
                className={FIELD_CLASS}
              />
            </Field>

            <Field label="Next action date" className="sm:col-span-2">
              <input
                type="date"
                value={draft.next_action_date}
                onChange={(event) =>
                  set('next_action_date', event.target.value)
                }
                className={FIELD_CLASS}
              />
            </Field>

            <Field label="Notes" className="sm:col-span-2">
              <textarea
                rows={5}
                value={draft.notes}
                onChange={(event) => set('notes', event.target.value)}
                placeholder="Who you spoke to, what they asked, what you promised to send."
                className={`${FIELD_CLASS} resize-y leading-relaxed`}
              />
            </Field>
          </div>
        </div>

        <footer className="flex flex-shrink-0 items-center justify-end gap-2 border-t border-border bg-card px-5 py-3">
          <span className="mr-auto text-[12px] text-text-faint">
            {isDirty ? 'Unsaved changes' : 'All changes saved'}
          </span>
          <button
            type="button"
            onClick={() => (isDirty ? setConfirmingDiscard(true) : onClose())}
            className="min-h-[42px] rounded-btn border border-border-input bg-card px-4 py-2 text-[13px] font-medium text-text-primary"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={!isDirty || isSaving || Boolean(jobUrlError)}
            className="flex min-h-[42px] items-center gap-2 rounded-btn bg-coral px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {isSaving && <Spinner size={14} className="text-white" />}
            {isSaving ? 'Saving...' : 'Save changes'}
          </button>
        </footer>
      </aside>

      <ConfirmModal
        open={confirmingDiscard}
        title="Discard unsaved changes?"
        description="The edits to this application will be lost."
        confirmLabel="Discard"
        onConfirm={() => {
          setConfirmingDiscard(false)
          setDraft(initial)
          onClose()
        }}
        onCancel={() => setConfirmingDiscard(false)}
      />
    </>
  )
}
