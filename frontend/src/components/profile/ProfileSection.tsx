import { useEffect, useState, type ReactNode } from 'react'
import { Pencil, Undo2 } from 'lucide-react'
import ConfirmModal from '../common/ConfirmModal'

/** Save lifecycle for one section, driven by `useProfileSectionEditor`. */
export type SectionSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

interface ProfileSectionProps {
  title: string
  description?: string
  isEditing: boolean
  /** True when the draft has moved away from the last saved value. */
  isDirty?: boolean
  status?: SectionSaveStatus
  /** Shown inline under the header for a problem that is not about one field. */
  errorMessage?: string | null
  /** A quieter aside — "Empty rows were removed" after a save. */
  note?: string | null
  onEdit: () => void
  onSave: () => void
  onDiscard: () => void
  children: ReactNode
}

/**
 * One profile section rendered as a card, with an explicit Edit / Save /
 * Discard header and inline save feedback next to the title.
 *
 * Editing is per section rather than per field so a user filling in a whole
 * role is not fighting a dozen separate toggles — and, since a role is only
 * valid once its title *and* company are filled in, per section is also the
 * smallest unit that can be validated as a whole.
 *
 * Discard asks first whenever there is something to lose. Escape and Cancel
 * both keep the user editing, which is the safe answer for a dialog whose
 * other button destroys work.
 */
export default function ProfileSection({
  title,
  description,
  isEditing,
  isDirty = false,
  status = 'idle',
  errorMessage,
  note,
  onEdit,
  onSave,
  onDiscard,
  children,
}: ProfileSectionProps) {
  // The label lingers after the status returns to idle so it can fade out
  // rather than vanish.
  const [flashLabel, setFlashLabel] = useState('')
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)

  useEffect(() => {
    if (status === 'saving') setFlashLabel('Saving...')
    else if (status === 'saved') setFlashLabel('Saved')
  }, [status])

  // A dialog left open behind a section that is no longer being edited would
  // discard nothing and confuse everything.
  useEffect(() => {
    if (!isEditing) setConfirmingDiscard(false)
  }, [isEditing])

  const flashVisible = status === 'saving' || status === 'saved'
  const isSaving = status === 'saving'

  function handleDiscard() {
    if (isDirty) {
      setConfirmingDiscard(true)
      return
    }
    onDiscard()
  }

  return (
    <section className="rounded-card border border-border bg-card p-4 sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h2 className="font-serif text-[17px] font-medium text-teal-ink">
              {title}
            </h2>
            {isDirty && (
              <span className="rounded-pill bg-amber-light px-2 py-[2px] text-[10px] font-medium uppercase tracking-[0.5px] text-amber-ink">
                Unsaved changes
              </span>
            )}
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
            <p className="mt-0.5 text-[12px] leading-relaxed text-text-muted">{description}</p>
          )}
        </div>

        {isEditing ? (
          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleDiscard}
              disabled={isSaving}
              className="flex min-h-[40px] items-center gap-1.5 rounded-btn border border-border-input bg-card px-3 py-1.5 text-[12px] font-medium text-text-secondary transition-colors hover:border-teal-soft hover:text-teal-ink disabled:opacity-50 sm:min-h-0"
            >
              <Undo2 size={13} />
              Discard
            </button>
            <button
              type="button"
              onClick={onSave}
              // Nothing to send is not an error worth a message — the button
              // simply has nothing to do until the draft moves.
              disabled={!isDirty || isSaving}
              className="flex min-h-[40px] items-center gap-1.5 rounded-btn bg-coral px-3.5 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-40 sm:min-h-0"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={onEdit}
            className="flex min-h-[40px] flex-shrink-0 items-center gap-1.5 rounded-btn border border-border-input bg-card px-3 py-1.5 text-[12px] font-medium text-text-secondary transition-colors hover:border-teal-soft hover:text-teal-ink sm:min-h-0"
          >
            <Pencil size={13} />
            Edit
          </button>
        )}
      </div>

      {errorMessage && (
        <p
          role="alert"
          className="mb-3 rounded-input border border-coral/30 bg-coral-light px-3 py-2 text-[12px] leading-relaxed text-coral-ink"
        >
          {errorMessage}
        </p>
      )}

      {note && (
        <p className="mb-3 text-[12px] leading-relaxed text-text-muted">{note}</p>
      )}

      {children}

      <ConfirmModal
        open={confirmingDiscard}
        title="Discard unsaved changes?"
        description={`Your edits to ${title.toLowerCase()} will be thrown away and the last saved version restored.`}
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={() => {
          setConfirmingDiscard(false)
          onDiscard()
        }}
        onCancel={() => setConfirmingDiscard(false)}
      />
    </section>
  )
}
