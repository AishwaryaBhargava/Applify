import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import ProfileField from './ProfileField'
import { errorKey, type SectionErrorMap } from '../../lib/profileValidation'

/**
 * `lines` edits a `string[]` as a textarea, one item per line — the shape
 * highlights and technologies take. `toggle` edits a boolean.
 */
export type EntryFieldKind = 'text' | 'textarea' | 'lines' | 'toggle'

export interface EntryFieldSpec<T> {
  key: Extract<keyof T, string>
  label: string
  kind?: EntryFieldKind
  placeholder?: string
  hint?: string
  rows?: number
  /** Spans both columns of the edit grid. */
  wide?: boolean
  /** Asterisk, `aria-required`, and a 422 waiting on the other side. */
  required?: boolean
  /** Asterisk with a tooltip, for a "one of these two" requirement. */
  requiredNote?: string
  /** Backend limit for this field. Text inputs enforce it themselves. */
  maxLength?: number
  /** `lines` only: the per-item limit and how many items are allowed. */
  itemMaxLength?: number
  maxItems?: number
}

interface ProfileEntryListProps<T> {
  entries: T[]
  fields: EntryFieldSpec<T>[]
  isEditing: boolean
  makeEmpty: () => T
  /** Receives the whole array — PATCH /profile replaces a section wholesale. */
  onChange: (entries: T[]) => void
  /** This section's field errors, keyed `"<index>.<field>"`. */
  errors?: SectionErrorMap
  renderView: (entry: T, index: number) => ReactNode
  addLabel: string
  emptyText: string
}

function toText(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return ''
}

function toLines(value: unknown): string {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string').join('\n')
    : ''
}

function fromLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

/** Below this many lines the counter is noise; above it, it is a warning. */
const COUNTER_FROM_LINES = 15

interface LinesFieldProps {
  label: string
  value: string[]
  rows: number
  placeholder?: string
  hint?: string
  error?: string
  itemMaxLength: number
  /** Omitted where the backend caps nothing (project technologies). */
  maxItems?: number
  id: string
  onChange: (value: string[]) => void
}

/**
 * A `string[]` edited as one-per-line text.
 *
 * The raw text is held locally because the parsed value cannot represent what
 * someone is halfway through typing: pressing Enter produces a trailing empty
 * line, which `fromLines` drops, which would put the caret back on the line
 * above. Local text keeps the caret where the user put it while the parsed
 * array still flows to the section draft on every keystroke.
 *
 * Over-long input is refused rather than truncated. Silently cutting a bullet
 * off at 500 characters is the same silent data loss the save-on-blur editor
 * used to commit; telling the user their bullet is too long lets them shorten
 * it themselves.
 */
function LinesField({
  label,
  value,
  rows,
  placeholder,
  hint,
  error,
  itemMaxLength,
  maxItems,
  id,
  onChange,
}: LinesFieldProps) {
  const [text, setText] = useState(() => toLines(value))
  const [blocked, setBlocked] = useState<string | null>(null)
  const focusedRef = useRef(false)

  // Re-sync when the array changes underneath — a discard, a server-confirmed
  // save — but never while this box has the caret.
  useEffect(() => {
    if (!focusedRef.current) setText(toLines(value))
  }, [value])

  const lines = fromLines(text)
  const showCounter = maxItems !== undefined && lines.length > COUNTER_FROM_LINES
  const message = error ?? blocked

  function handleChange(next: string) {
    const nextLines = fromLines(next)
    const longest = nextLines.reduce((max, line) => Math.max(max, line.length), 0)
    if (longest > itemMaxLength) {
      setBlocked(
        `Each ${label.toLowerCase().replace(/s$/, '')} must be ${itemMaxLength} characters or less`,
      )
      return
    }
    if (maxItems !== undefined && nextLines.length > maxItems) {
      setBlocked(`Keep ${label.toLowerCase()} to ${maxItems} or fewer`)
      return
    }
    setBlocked(null)
    setText(next)
    onChange(nextLines)
  }

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1 block text-[11px] font-medium uppercase tracking-[0.7px] text-text-muted sm:text-[10px]"
      >
        {label}
      </label>
      <textarea
        id={id}
        value={text}
        rows={rows}
        placeholder={placeholder}
        aria-invalid={message ? true : undefined}
        aria-describedby={message ? `${id}-error` : undefined}
        onFocus={() => {
          focusedRef.current = true
        }}
        onBlur={() => {
          focusedRef.current = false
        }}
        onChange={(event) => handleChange(event.target.value)}
        className={`w-full resize-y rounded-input bg-bg px-3 py-2 text-[16px] leading-relaxed text-text-primary outline-none transition-colors placeholder:text-text-faint focus:bg-card sm:text-[13px] ${
          message
            ? 'border border-coral focus:border-coral'
            : 'border border-border-input focus:border-teal-medium'
        }`}
      />
      {message && (
        <p
          id={`${id}-error`}
          role="alert"
          className="mt-1 text-[12px] leading-relaxed text-coral-ink"
        >
          {message}
        </p>
      )}
      <div className="mt-1 flex items-baseline justify-between gap-2">
        {hint ? (
          <p className="text-[12px] leading-relaxed text-text-faint sm:text-[11px]">
            {hint}
          </p>
        ) : (
          <span />
        )}
        {showCounter && (
          <span
            className={`flex-shrink-0 text-[11px] tabular-nums ${
              lines.length >= (maxItems ?? 0) ? 'text-coral' : 'text-text-faint'
            }`}
          >
            {lines.length}/{maxItems}
          </span>
        )}
      </div>
    </div>
  )
}

/** True when nothing in the entry has been typed into yet. */
function isEmptyEntry(entry: unknown): boolean {
  if (!entry || typeof entry !== 'object') return true
  return Object.values(entry as Record<string, unknown>).every((value) => {
    if (Array.isArray(value)) return value.length === 0
    if (typeof value === 'string') return value.trim() === ''
    // Booleans do not count as content: a row where only "I work here now" is
    // ticked still says nothing about the job.
    return typeof value === 'boolean' || value === null || value === undefined
  })
}

/**
 * The repeated-entry sections (experience, education, certifications,
 * projects): a stack of cards in view mode, a stack of inline forms with
 * add / remove in edit mode.
 *
 * Every change hands the parent the complete array, because the backend
 * replaces a section wholesale rather than merging into it. Nothing here
 * saves — the section header owns that.
 */
export default function ProfileEntryList<T>({
  entries,
  fields,
  isEditing,
  makeEmpty,
  onChange,
  errors = {},
  renderView,
  addLabel,
  emptyText,
}: ProfileEntryListProps<T>) {
  const listId = useId()
  // The index whose Remove button has been armed, awaiting a second click. A
  // modal for one row of a form is too heavy; losing a filled-in role to a
  // mis-click is too expensive for a single click.
  const [confirmingRemove, setConfirmingRemove] = useState<number | null>(null)
  // Set by "Add entry" so the new row's first required box takes the caret.
  const [focusIndex, setFocusIndex] = useState<number | null>(null)

  const firstFocusKey = (fields.find((field) => field.required) ?? fields[0])?.key

  useEffect(() => {
    if (focusIndex === null || !firstFocusKey) return
    const element = document.getElementById(
      `${listId}-${focusIndex}-${firstFocusKey}`,
    )
    element?.focus()
    setFocusIndex(null)
  }, [focusIndex, firstFocusKey, listId])

  // An armed Remove that survived into view mode would fire on the next edit.
  useEffect(() => {
    if (!isEditing) setConfirmingRemove(null)
  }, [isEditing])

  function patchEntry(index: number, key: string, next: unknown) {
    onChange(
      entries.map((entry, i) =>
        i === index ? ({ ...entry, [key]: next } as T) : entry,
      ),
    )
  }

  function removeEntry(index: number) {
    setConfirmingRemove(null)
    onChange(entries.filter((_, i) => i !== index))
  }

  if (!isEditing) {
    if (entries.length === 0) {
      return <p className="text-[13px] text-text-faint">{emptyText}</p>
    }
    return (
      <div className="flex flex-col gap-3">
        {entries.map((entry, index) => (
          <div
            key={index}
            className="rounded-box border border-border bg-surface px-3.5 py-3 sm:px-4"
          >
            {renderView(entry, index)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {entries.map((entry, index) => {
        const armed = confirmingRemove === index
        const hasError = fields.some((field) => errors[errorKey(index, field.key)])

        return (
          <div
            key={index}
            className={`rounded-box border bg-surface px-3.5 py-4 sm:px-4 ${
              hasError ? 'border-coral/50' : 'border-border'
            }`}
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {fields.map((field) => {
                const raw = (entry as Record<string, unknown>)[field.key]
                const kind = field.kind ?? 'text'
                const span = field.wide || kind !== 'text' ? 'sm:col-span-2' : ''
                const fieldId = `${listId}-${index}-${field.key}`
                const error = errors[errorKey(index, field.key)]

                if (kind === 'toggle') {
                  return (
                    <label
                      key={field.key}
                      className="flex items-center gap-2 text-[13px] text-text-primary sm:col-span-2"
                    >
                      <input
                        type="checkbox"
                        checked={raw === true}
                        onChange={(event) =>
                          patchEntry(index, field.key, event.target.checked)
                        }
                        className="h-3.5 w-3.5 accent-[#1D9E75]"
                      />
                      {field.label}
                    </label>
                  )
                }

                if (kind === 'lines') {
                  return (
                    <div key={field.key} className={span}>
                      <LinesField
                        id={fieldId}
                        label={field.label}
                        value={Array.isArray(raw) ? (raw as string[]) : []}
                        rows={field.rows ?? 4}
                        placeholder={field.placeholder}
                        hint={field.hint ?? 'One per line'}
                        error={error}
                        itemMaxLength={field.itemMaxLength ?? 500}
                        maxItems={field.maxItems}
                        onChange={(next) => patchEntry(index, field.key, next)}
                      />
                    </div>
                  )
                }

                return (
                  <div key={field.key} className={span}>
                    <ProfileField
                      id={fieldId}
                      label={field.label}
                      isEditing
                      value={toText(raw)}
                      multiline={kind === 'textarea'}
                      rows={field.rows ?? 3}
                      placeholder={field.placeholder}
                      hint={field.hint}
                      required={field.required}
                      requiredNote={field.requiredNote}
                      error={error}
                      maxLength={field.maxLength}
                      onChange={(next) => patchEntry(index, field.key, next)}
                    />
                  </div>
                )
              })}
            </div>

            {armed ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-[12px] text-text-secondary">Remove?</span>
                <button
                  type="button"
                  onClick={() => removeEntry(index)}
                  className="min-h-[36px] rounded-btn bg-coral px-3 py-1 text-[12px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingRemove(null)}
                  className="min-h-[36px] rounded-btn border border-border-input px-3 py-1 text-[12px] font-medium text-text-secondary hover:border-teal-soft hover:text-teal-ink"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => {
                  // A row with nothing in it has nothing to lose.
                  if (isEmptyEntry(entry)) removeEntry(index)
                  else setConfirmingRemove(index)
                }}
                className="mt-3 flex min-h-[40px] items-center gap-1.5 text-[12px] font-medium text-coral underline-offset-2 hover:underline sm:min-h-0"
              >
                <Trash2 size={13} />
                Remove entry
              </button>
            )}
          </div>
        )
      })}

      <button
        type="button"
        onClick={() => {
          onChange([...entries, makeEmpty()])
          setFocusIndex(entries.length)
        }}
        className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-btn border border-dashed border-border-input px-3 py-2.5 text-[12px] font-medium text-teal-deep transition-colors hover:border-teal-soft hover:bg-teal-light"
      >
        <Plus size={14} />
        {addLabel}
      </button>
    </div>
  )
}
