import { useState, type KeyboardEvent } from 'react'
import { Plus, X } from 'lucide-react'

interface ProfileChipsProps {
  values: string[]
  isEditing: boolean
  /** Skills get the light-teal tag treatment; achievements stay neutral. */
  tone?: 'teal' | 'neutral'
  placeholder?: string
  emptyText: string
  /** Receives the whole array — the backend replaces a section wholesale. */
  onChange: (values: string[]) => void
}

const toneClasses: Record<'teal' | 'neutral', string> = {
  teal: 'bg-teal-light text-teal-ink',
  neutral: 'bg-surface-warm text-text-primary',
}

/**
 * The flat string sections (skills, achievements) as tags: read-only pills in
 * view mode, removable pills plus an add box in edit mode.
 */
export default function ProfileChips({
  values,
  isEditing,
  tone = 'teal',
  placeholder = 'Add and press Enter',
  emptyText,
  onChange,
}: ProfileChipsProps) {
  const [entry, setEntry] = useState('')

  function commit() {
    const next = entry.trim()
    if (!next) return
    setEntry('')
    const exists = values.some(
      (value) => value.trim().toLowerCase() === next.toLowerCase(),
    )
    if (exists) return
    onChange([...values, next])
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      commit()
      return
    }
    // Backspace on an empty box removes the last tag, as tag inputs do.
    if (event.key === 'Backspace' && !entry && values.length) {
      onChange(values.slice(0, -1))
    }
  }

  if (!isEditing && values.length === 0) {
    return <p className="text-[13px] text-text-faint">{emptyText}</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {values.map((value, index) => (
            <li
              key={`${value}-${index}`}
              className={`flex max-w-full items-start gap-1.5 rounded-pill px-2.5 py-[5px] text-[12px] leading-relaxed ${toneClasses[tone]}`}
            >
              <span className="min-w-0 break-words">{value}</span>
              {isEditing && (
                <button
                  type="button"
                  aria-label={`Remove ${value}`}
                  onClick={() => onChange(values.filter((_, i) => i !== index))}
                  className="mt-[3px] flex-shrink-0 opacity-60 hover:opacity-100"
                >
                  <X size={12} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isEditing && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={entry}
            placeholder={placeholder}
            onChange={(event) => setEntry(event.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={commit}
            className="min-w-0 flex-1 rounded-input border border-border-input bg-bg px-3 py-2 text-[13px] text-text-primary outline-none transition-colors placeholder:text-text-faint focus:border-teal-medium focus:bg-card"
          />
          <button
            type="button"
            onClick={commit}
            className="flex flex-shrink-0 items-center gap-1 rounded-btn border border-border-input px-3 py-2 text-[12px] font-medium text-teal-deep transition-colors hover:border-teal-soft hover:bg-teal-light"
          >
            <Plus size={13} />
            Add
          </button>
        </div>
      )}
    </div>
  )
}
