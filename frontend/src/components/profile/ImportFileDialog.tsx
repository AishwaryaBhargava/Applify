import { useCallback, useEffect, useId, useState } from 'react'
import { X } from 'lucide-react'
import ProfileImportUpload from './ProfileImportUpload'

interface ImportFileDialogProps {
  open: boolean
  onClose: () => void
}

/**
 * The import uploader in a dialog, for the profile page's "Import from a file"
 * action.
 *
 * Escape and the backdrop both close it, except while a read is in flight:
 * unmounting the uploader mid-request would throw away an answer the user has
 * already waited half a minute for, and there is no way to ask for it again
 * without paying for the read a second time.
 */
export default function ImportFileDialog({ open, onClose }: ImportFileDialogProps) {
  const titleId = useId()
  const [isBusy, setIsBusy] = useState(false)

  const close = useCallback(() => {
    if (isBusy) return
    onClose()
  }, [isBusy, onClose])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  // A dialog that was closed while busy would leave the flag stuck on.
  useEffect(() => {
    if (!open) setIsBusy(false)
  }, [open])

  if (!open) return null

  return (
    <div
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/20 p-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="my-auto max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-panel border border-border bg-card p-5 text-left sm:p-6"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="font-serif text-lg font-medium text-teal-ink"
            >
              Import from a file
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-text-secondary">
              A spreadsheet of roles, a list of publications, an export from
              another tool. Applify reads it, merges it with what it already
              knows, and shows you the changes before anything is saved.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={isBusy}
            aria-label="Close"
            className="-mr-1 -mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-input text-text-muted transition-colors hover:bg-surface-warm hover:text-text-primary disabled:opacity-40"
          >
            <X size={16} />
          </button>
        </div>

        <ProfileImportUpload
          onBusyChange={setIsBusy}
          onImported={onClose}
          footer={
            <button
              type="button"
              onClick={close}
              disabled={isBusy}
              className="mx-auto flex min-h-[40px] items-center justify-center px-4 text-[13px] text-text-muted underline-offset-2 hover:text-text-primary hover:underline disabled:opacity-40"
            >
              Cancel
            </button>
          }
        />
      </div>
    </div>
  )
}
