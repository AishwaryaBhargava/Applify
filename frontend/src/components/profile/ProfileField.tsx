import { useId } from 'react'

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
  /** Marks the field with an asterisk and `aria-required`. */
  required?: boolean
  /**
   * An asterisk with a tooltip, for a field that is required only as part of a
   * pair (education wants a degree *or* a field of study). No `aria-required`:
   * neither box on its own is mandatory.
   */
  requiredNote?: string
  /** The message for this field, from the section's error map. */
  error?: string
  /** Hard cap, enforced by the input itself. Mirrors the backend's limit. */
  maxLength?: number
  /**
   * Show a live character count once the value reaches this length — quiet
   * until the limit is close enough to matter.
   */
  counterFrom?: number
  /** Lets the parent focus this input after adding a row. */
  id?: string
  /** Fires per keystroke: there is no autosave left for it to trigger. */
  onChange: (value: string) => void
}

/**
 * A single editable profile field.
 *
 * Fully controlled. It used to hold its own draft and commit on blur, because
 * blur was what triggered a save; now that saving is a button, local state
 * would only be a second copy of the section draft to keep in sync — and the
 * "Unsaved changes" pill has to light up on the first keystroke, not on the
 * way out of the box.
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
  required = false,
  requiredNote,
  error,
  maxLength,
  counterFrom,
  id,
  onChange,
}: ProfileFieldProps) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  const errorId = `${fieldId}-error`
  const hintId = `${fieldId}-hint`

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

  const showCounter =
    counterFrom !== undefined &&
    maxLength !== undefined &&
    value.length >= counterFrom

  const shared = [
    'w-full rounded-input bg-bg px-3 py-2 text-[16px] text-text-primary outline-none transition-colors placeholder:text-text-faint focus:bg-card sm:text-[13px]',
    error
      ? 'border border-coral focus:border-coral'
      : 'border border-border-input focus:border-teal-medium',
  ].join(' ')

  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') ||
    undefined

  const inputProps = {
    id: fieldId,
    value,
    placeholder,
    maxLength,
    'aria-required': required || undefined,
    'aria-invalid': error ? (true as const) : undefined,
    'aria-describedby': describedBy,
    className: shared,
  }

  return (
    <div>
      <label
        htmlFor={fieldId}
        className="mb-1 block text-[11px] font-medium uppercase tracking-[0.7px] text-text-muted sm:text-[10px]"
      >
        {label}
        {(required || requiredNote) && (
          <span
            aria-hidden="true"
            title={requiredNote ?? 'Required'}
            className="ml-0.5 text-coral"
          >
            *
          </span>
        )}
      </label>
      {multiline ? (
        <textarea
          {...inputProps}
          rows={rows}
          onChange={(event) => onChange(event.target.value)}
          className={`${shared} resize-y leading-relaxed`}
        />
      ) : (
        <input
          {...inputProps}
          type="text"
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {error && (
        <p id={errorId} role="alert" className="mt-1 text-[12px] leading-relaxed text-coral-ink">
          {error}
        </p>
      )}
      {(hint || showCounter) && (
        <div className="mt-1 flex items-baseline justify-between gap-2">
          {hint ? (
            <p
              id={hintId}
              className="text-[12px] leading-relaxed text-text-faint sm:text-[11px]"
            >
              {hint}
            </p>
          ) : (
            <span />
          )}
          {showCounter && (
            <span
              className={`flex-shrink-0 text-[11px] tabular-nums ${
                value.length >= (maxLength ?? 0) ? 'text-coral' : 'text-text-faint'
              }`}
            >
              {value.length}/{maxLength}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
