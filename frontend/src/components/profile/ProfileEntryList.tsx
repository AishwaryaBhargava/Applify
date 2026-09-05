import type { ReactNode } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import ProfileField from './ProfileField'

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
}

interface ProfileEntryListProps<T> {
  entries: T[]
  fields: EntryFieldSpec<T>[]
  isEditing: boolean
  makeEmpty: () => T
  /** Receives the whole array — PATCH /profile replaces a section wholesale. */
  onChange: (entries: T[]) => void
  /**
   * Receives the array with a blank entry appended. Kept separate from
   * `onChange` so the parent can hold it locally: the backend drops entries
   * with no content, so saving a blank one would delete the card the user is
   * about to type into.
   */
  onAdd: (entries: T[]) => void
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

/**
 * The repeated-entry sections (experience, education, certifications,
 * projects): a stack of cards in view mode, a stack of inline forms with
 * add / remove in edit mode.
 *
 * Every change hands the parent the complete array, because the backend
 * replaces a section wholesale rather than merging into it.
 */
export default function ProfileEntryList<T>({
  entries,
  fields,
  isEditing,
  makeEmpty,
  onChange,
  onAdd,
  renderView,
  addLabel,
  emptyText,
}: ProfileEntryListProps<T>) {
  function patchEntry(index: number, key: string, next: unknown) {
    onChange(
      entries.map((entry, i) =>
        i === index ? ({ ...entry, [key]: next } as T) : entry,
      ),
    )
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
            className="rounded-box border border-border bg-surface px-4 py-3"
          >
            {renderView(entry, index)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {entries.map((entry, index) => (
        <div
          key={index}
          className="rounded-box border border-border bg-surface px-4 py-4"
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {fields.map((field) => {
              const raw = (entry as Record<string, unknown>)[field.key]
              const kind = field.kind ?? 'text'
              const span = field.wide || kind !== 'text' ? 'sm:col-span-2' : ''

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

              return (
                <div key={field.key} className={span}>
                  <ProfileField
                    label={field.label}
                    isEditing
                    value={kind === 'lines' ? toLines(raw) : toText(raw)}
                    multiline={kind === 'lines' || kind === 'textarea'}
                    rows={field.rows ?? (kind === 'lines' ? 4 : 3)}
                    placeholder={field.placeholder}
                    hint={
                      field.hint ?? (kind === 'lines' ? 'One per line' : undefined)
                    }
                    onCommit={(next) =>
                      patchEntry(
                        index,
                        field.key,
                        kind === 'lines' ? fromLines(next) : next,
                      )
                    }
                  />
                </div>
              )
            })}
          </div>

          <button
            type="button"
            onClick={() => onChange(entries.filter((_, i) => i !== index))}
            className="mt-3 flex items-center gap-1.5 text-[12px] font-medium text-coral underline-offset-2 hover:underline"
          >
            <Trash2 size={13} />
            Remove entry
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={() => onAdd([...entries, makeEmpty()])}
        className="flex items-center justify-center gap-1.5 rounded-btn border border-dashed border-border-input px-3 py-2.5 text-[12px] font-medium text-teal-deep transition-colors hover:border-teal-soft hover:bg-teal-light"
      >
        <Plus size={14} />
        {addLabel}
      </button>
    </div>
  )
}
