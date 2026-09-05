import { useEffect, useState, type ReactNode } from 'react'
import { Check, Pencil } from 'lucide-react'

/** Save lifecycle for one section, driven by `useProfileSectionEditor`. */
export type SectionSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

interface ProfileSectionProps {
  title: string
  description?: string
  isEditing: boolean
  onToggleEdit: () => void
  status?: SectionSaveStatus
  /** Shown inline under the header when a save fails. */
  errorMessage?: string | null
  children: ReactNode
}

/**
 * One profile section rendered as a card, with a section-level Edit / Done
 * toggle and inline save feedback next to the title.
 *
 * Editing is per section rather than per field so a user filling in a whole
 * role is not fighting a dozen separate toggles.
 */
export default function ProfileSection({
  title,
  description,
  isEditing,
  onToggleEdit,
  status = 'idle',
  errorMessage,
  children,
}: ProfileSectionProps) {
  // The label lingers after the status returns to idle so it can fade out
  // rather than vanish.
  const [flashLabel, setFlashLabel] = useState('')

  useEffect(() => {
    if (status === 'saving') setFlashLabel('Saving...')
    else if (status === 'saved') setFlashLabel('Saved')
  }, [status])

  const flashVisible = status === 'saving' || status === 'saved'

  return (
    <section className="rounded-card border border-border bg-card p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h2 className="font-serif text-[17px] font-medium text-teal-ink">
              {title}
            </h2>
            <span
              aria-live="polite"
              className={`text-[11px] font-medium transition-opacity duration-500 ${
                flashVisible ? 'opacity-100' : 'opacity-0'
              } ${status === 'saving' ? 'text-text-muted' : 'text-teal-medium'}`}
            >
              {flashLabel}
            </span>
          </div>
          {description && (
            <p className="mt-0.5 text-[12px] text-text-muted">{description}</p>
          )}
        </div>

        <button
          type="button"
          onClick={onToggleEdit}
          className={`flex flex-shrink-0 items-center gap-1.5 rounded-btn border px-3 py-1.5 text-[12px] font-medium transition-colors ${
            isEditing
              ? 'border-teal-medium bg-teal-light text-teal-ink'
              : 'border-border-input bg-card text-text-secondary hover:border-teal-soft hover:text-teal-ink'
          }`}
        >
          {isEditing ? <Check size={13} /> : <Pencil size={13} />}
          {isEditing ? 'Done' : 'Edit'}
        </button>
      </div>

      {errorMessage && (
        <p
          role="alert"
          className="mb-3 rounded-input border border-coral/30 bg-coral-light px-3 py-2 text-[12px] leading-relaxed text-coral-ink"
        >
          {errorMessage}
        </p>
      )}

      {children}
    </section>
  )
}
