import { useEffect, useRef, useState } from 'react'

interface ProfileFieldProps {
  label: string
  value: string
  /** View mode renders plain text; edit mode renders an input. */
  isEditing: boolean
  multiline?: boolean
  rows?: number
  placeholder?: string
  /** Shown under the input in edit mode (e.g. "One per line"). */
  hint?: string
  /** Text shown in view mode when the value is empty. */
  emptyText?: string
  /** Drops the label in view mode when the section title already says it. */
  hideLabelInView?: boolean
  /** Commits the edited value to the parent. Fired on blur, never per keystroke. */
  onCommit: (value: string) => void
}

/**
 * A single editable profile field.
 *
 * The draft is local while the field has focus and is committed to the parent
 * on blur, so a section save is triggered once per field rather than once per
 * keystroke. External changes (a server-confirmed save, an entry removed above
 * this one) flow back in through `value`.
 */
export default function ProfileField({
  label,
  value,
  isEditing,
  multiline = false,
  rows = 3,
  placeholder,
  hint,
  emptyText = 'Not set',
  hideLabelInView = false,
  onCommit,
}: ProfileFieldProps) {
  const [draft, setDraft] = useState(value)
  const isFocusedRef = useRef(false)

  // Re-sync when the value changes underneath us, but never while the user is
  // typing into this field.
  useEffect(() => {
    if (!isFocusedRef.current) setDraft(value)
  }, [value])

  if (!isEditing) {
    return (
      <div>
        {!hideLabelInView && (
          <span className="mb-1 block text-[11px] font-medium uppercase tracking-[0.7px] text-text-faint sm:text-[10px]">
            {label}
          </span>
        )}
        <p
          className={`whitespace-pre-wrap text-[13px] leading-relaxed ${
            value.trim() ? 'text-text-primary' : 'text-text-faint'
          }`}
        >
          {value.trim() || emptyText}
        </p>
      </div>
    )
  }

  const shared =
    'w-full rounded-input border border-border-input bg-bg px-3 py-2 text-[16px] text-text-primary outline-none transition-colors placeholder:text-text-faint focus:border-teal-medium focus:bg-card sm:text-[13px]'

  return (
    <div>
      <label className="mb-1 block text-[11px] font-medium uppercase tracking-[0.7px] text-text-muted sm:text-[10px]">
        {label}
      </label>
      {multiline ? (
        <textarea
          value={draft}
          rows={rows}
          placeholder={placeholder}
          onFocus={() => {
            isFocusedRef.current = true
          }}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => {
            isFocusedRef.current = false
            if (draft !== value) onCommit(draft)
          }}
          className={`${shared} resize-y leading-relaxed`}
        />
      ) : (
        <input
          type="text"
          value={draft}
          placeholder={placeholder}
          onFocus={() => {
            isFocusedRef.current = true
          }}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => {
            isFocusedRef.current = false
            if (draft !== value) onCommit(draft)
          }}
          className={shared}
        />
      )}
      {hint && (
        <p className="mt-1 text-[12px] leading-relaxed text-text-faint sm:text-[11px]">
          {hint}
        </p>
      )}
    </div>
  )
}
