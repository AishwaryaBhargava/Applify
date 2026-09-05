import { useEffect, useState, type KeyboardEvent } from 'react'
import { Plus, X } from 'lucide-react'

interface ProfileChipsProps {
  values: string[]
  isEditing: boolean
  /** Skills get the light-teal tag treatment; achievements stay neutral. */
  tone?: 'teal' | 'neutral'
  placeholder?: string
  emptyText: string
  /** Backend limit for one chip. Mirrors `skills` 60 / `achievements` 500. */
  maxLength?: number
  /** Singular noun for the messages ("Each skill must be..."). */
  itemLabel?: string
  /** The section-level message, when a 422 lands on the list as a whole. */
  error?: string
  /** Receives the whole array — the backend replaces a section wholesale. */
  onChange: (values: string[]) => void
}

const toneClasses: Record<'teal' | 'neutral', string> = {
  teal: 'bg-teal-light text-teal-ink',
  neutral: 'bg-surface-warm text-text-primary',
}

/** How long a rejection message stays before it stops being the answer. */
const NOTICE_MS = 2500

/**
 * The flat string sections (skills, achievements) as tags: read-only pills in
 * view mode, removable pills plus an add box in edit mode.
 *
 * The backend folds duplicates case-insensitively and drops blanks, so a chip
 * that would be swallowed is refused here with a reason instead — "Already
 * added" beats a tag that never appears and never explains why. Edits go into
 * the section draft like any other, and are saved by the section's Save.
 */
export default function ProfileChips({
  values,
  isEditing,
  tone = 'teal',
  placeholder = 'Add and press Enter',
  emptyText,
  maxLength,
  itemLabel = 'entry',
  error,
  onChange,
}: ProfileChipsProps) {
  const [entry, setEntry] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS)
    return () => window.clearTimeout(timer)
  }, [notice])

  function commit() {
    const next = entry.trim()
    // An empty box is someone who tabbed past, not a mistake worth a message.
    if (!next) {
      setEntry('')
      return
    }
    if (maxLength !== undefined && next.length > maxLength) {
      setNotice(`Each ${itemLabel} must be ${maxLength} characters or less`)
      return
    }
    const exists = values.some(
      (value) => value.trim().toLowerCase() === next.toLowerCase(),
    )
    if (exists) {
      // The text stays in the box: the user can see what was rejected and
      // edit it into something new.
      setNotice('Already added')
      return
    }
    setNotice(null)
    setEntry('')
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

  const message = error ?? notice

  return (
    <div className="flex flex-col gap-3">
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {values.map((value, index) => (
            <li
              key={`${value}-${index}`}
              className={`flex max-w-full items-start gap-1.5 rounded-pill px-2.5 py-2 text-[12px] leading-relaxed sm:py-[5px] ${toneClasses[tone]}`}
            >
              <span className="min-w-0 break-words">{value}</span>
              {isEditing && (
                <button
                  type="button"
                  aria-label={`Remove ${value}`}
                  onClick={() => onChange(values.filter((_, i) => i !== index))}
                  className="-my-1 -mr-1.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full opacity-60 hover:bg-black/5 hover:opacity-100 sm:my-0 sm:mr-0 sm:mt-[3px] sm:h-auto sm:w-auto"
                >
                  <X size={12} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isEditing && (
        <div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={entry}
              placeholder={placeholder}
              maxLength={maxLength}
              aria-invalid={message ? true : undefined}
              onChange={(event) => {
                setEntry(event.target.value)
                if (notice) setNotice(null)
              }}
              onKeyDown={handleKeyDown}
              // Still committed on blur — with no autosave behind it this only
              // moves the chip into the draft, so a tag someone typed and then
              // reached for Save is not lost on the way to the button.
              onBlur={commit}
              className={`min-h-[44px] min-w-0 flex-1 rounded-input bg-bg px-3 py-2 text-[16px] text-text-primary outline-none transition-colors placeholder:text-text-faint focus:bg-card sm:min-h-0 sm:text-[13px] ${
                message
                  ? 'border border-coral focus:border-coral'
                  : 'border border-border-input focus:border-teal-medium'
              }`}
            />
            <button
              type="button"
              onClick={commit}
              className="flex min-h-[44px] flex-shrink-0 items-center gap-1 rounded-btn border border-border-input px-3.5 py-2 text-[12px] font-medium text-teal-deep transition-colors hover:border-teal-soft hover:bg-teal-light sm:min-h-0"
            >
              <Plus size={13} />
              Add
            </button>
          </div>
          {message && (
            <p role="alert" className="mt-1 text-[12px] leading-relaxed text-coral-ink">
              {message}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
