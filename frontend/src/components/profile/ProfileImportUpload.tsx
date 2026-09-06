import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { FileSpreadsheet, FileText, UploadCloud, X } from 'lucide-react'
import {
  IMPORT_ACCEPT,
  IMPORT_EXTENSIONS,
  IMPORT_MAX_BYTES,
  importProfileFile,
} from '../../services/profile'
import { apiErrorMessage, apiErrorStatus } from '../../services/api'
import { useProfileStore } from '../../store/profileStore'
import { pushToast } from '../../store/toastStore'
import Spinner from '../common/Spinner'

/** Where a successful import sends the user to review the proposed merge. */
export const IMPORT_REVIEW_PATH = '/profile/import'

/** Uploading is the file going up; analysing is the model reading and merging. */
type Stage = 'idle' | 'uploading' | 'analysing'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Human list of the accepted extensions, without the dots. */
const EXTENSION_LIST = IMPORT_EXTENSIONS.map((ext) => ext.slice(1).toUpperCase())
  .join(', ')
  .replace(/, ([^,]*)$/, ' or $1')

/** Returns a rejection message, or null when the file is acceptable. */
function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!IMPORT_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `That file type is not supported. Try ${EXTENSION_LIST}.`
  }
  if (file.size > IMPORT_MAX_BYTES) {
    return `That file is ${formatSize(file.size)}. The limit is 10MB.`
  }
  if (file.size === 0) return 'That file is empty. Try a different one.'
  return null
}

interface ProfileImportUploadProps {
  /** Called once the proposal is staged and the review screen is open. */
  onImported?: () => void
  /** Rendered under the dropzone — a Cancel button when this sits in a modal. */
  footer?: ReactNode
  /**
   * Reports whether a read is in flight, so a dialog hosting this can refuse to
   * close mid-upload rather than unmounting the component that is waiting on
   * the answer.
   */
  onBusyChange?: (busy: boolean) => void
}

/**
 * Drag-and-drop uploader for a supplementary file — a spreadsheet of roles, a
 * document listing publications, an exported JSON profile.
 *
 * Sibling to `ResumeUpload` rather than a mode of it: a resume upload *replaces*
 * the profile and lands on /profile, while this one saves nothing at all. It
 * posts to `/profile/import`, stages the merge preview in the store, and hands
 * the user to the review screen to decide what to keep.
 */
export default function ProfileImportUpload({
  onImported,
  footer,
  onBusyChange,
}: ProfileImportUploadProps) {
  const navigate = useNavigate()
  const setImportProposal = useProfileStore((state) => state.setImportProposal)

  const inputRef = useRef<HTMLInputElement>(null)
  const analysingTimerRef = useRef<number | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [progress, setProgress] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  const isBusy = stage !== 'idle'

  useEffect(
    () => () => {
      if (analysingTimerRef.current) window.clearTimeout(analysingTimerRef.current)
    },
    [],
  )

  useEffect(() => {
    onBusyChange?.(isBusy)
  }, [isBusy, onBusyChange])

  function acceptFile(candidate: File | undefined) {
    if (!candidate) return
    const message = validateFile(candidate)
    if (message) {
      setFile(null)
      setError(message)
      return
    }
    setError(null)
    setFile(candidate)
  }

  function clearSelection() {
    setFile(null)
    setError(null)
    setProgress(0)
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragging(false)
    if (isBusy) return
    acceptFile(event.dataTransfer.files?.[0])
  }

  async function handleImport() {
    if (!file || isBusy) return

    setError(null)
    setProgress(0)
    setStage('uploading')

    // A small spreadsheet can finish uploading before a single progress event
    // lands, so guarantee the "Analysing" copy appears either way.
    analysingTimerRef.current = window.setTimeout(() => {
      setStage((current) => (current === 'uploading' ? 'analysing' : current))
    }, 900)

    try {
      const proposal = await importProfileFile(file, (event) => {
        if (!event.total) return
        const percent = Math.round((event.loaded / event.total) * 100)
        setProgress(percent)
        if (percent >= 100) {
          setStage((current) => (current === 'uploading' ? 'analysing' : current))
        }
      })

      setImportProposal(proposal)
      setStage('idle')
      onImported?.()
      navigate(IMPORT_REVIEW_PATH)
    } catch (importError) {
      const status = apiErrorStatus(importError)
      const fallback =
        status === 422
          ? 'We could not read anything usable out of that file.'
          : 'We could not read that file. Please try again.'
      const message = apiErrorMessage(importError, fallback)
      setStage('idle')
      setProgress(0)
      setError(message)
      pushToast(message, 'error')
    } finally {
      if (analysingTimerRef.current) {
        window.clearTimeout(analysingTimerRef.current)
        analysingTimerRef.current = null
      }
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          if (!isBusy) setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`rounded-card border border-dashed bg-card px-5 py-8 text-center transition-colors sm:px-6 sm:py-10 ${
          isDragging ? 'border-teal-medium bg-teal-light' : 'border-border-input'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={IMPORT_ACCEPT}
          className="hidden"
          disabled={isBusy}
          onChange={(event) => acceptFile(event.target.files?.[0])}
        />

        {file ? (
          <div className="flex flex-col items-center gap-3">
            <div className="flex w-full max-w-sm items-center gap-3 rounded-box border border-border bg-surface px-3 py-2.5 text-left">
              <FileText size={18} className="flex-shrink-0 text-teal-deep" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-text-primary">
                  {file.name}
                </p>
                <p className="text-[11px] text-text-muted">
                  {formatSize(file.size)}
                </p>
              </div>
              {!isBusy && (
                <button
                  type="button"
                  onClick={clearSelection}
                  aria-label="Remove selected file"
                  className="flex-shrink-0 text-text-muted hover:text-text-primary"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => void handleImport()}
              disabled={isBusy}
              className="flex min-h-[44px] items-center justify-center gap-2 rounded-btn bg-coral px-5 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-60"
            >
              {isBusy && <Spinner size={14} className="text-white" />}
              {isBusy ? 'Working...' : 'Read this file'}
            </button>

            {!isBusy && (
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="text-[12px] text-teal-deep underline-offset-2 hover:underline"
              >
                Choose a different file
              </button>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isBusy}
            className="flex w-full cursor-pointer flex-col items-center justify-center gap-2"
          >
            <FileSpreadsheet size={24} className="text-teal-deep" />
            <span className="text-[14px] font-medium text-text-primary">
              Drop a spreadsheet or document here
            </span>
            <span className="text-[12px] text-text-muted">
              {EXTENSION_LIST}, up to 10MB
            </span>
            <span className="mt-1 text-[12px] font-medium text-teal-deep underline-offset-2 hover:underline">
              or browse your files
            </span>
          </button>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-input border border-coral/30 bg-coral-light px-3 py-2.5 text-[12px] leading-relaxed text-coral-ink"
        >
          {error}
        </p>
      )}

      {isBusy && (
        <div className="flex flex-col gap-3 rounded-box border border-border bg-card px-4 py-4">
          <div className="flex items-center gap-2">
            <UploadCloud size={15} className="flex-shrink-0 text-amber" />
            <p className="text-[13px] font-medium text-text-primary">
              {stage === 'uploading' ? 'Uploading' : 'Analysing'}
            </p>
          </div>

          {stage === 'uploading' ? (
            <div className="h-1 w-full overflow-hidden rounded-full bg-surface-warm">
              <div
                className="h-full rounded-full bg-amber transition-[width] duration-200"
                style={{ width: `${Math.max(progress, 4)}%` }}
              />
            </div>
          ) : (
            // No percentage here on purpose: the server gives no progress for
            // the model pass, and a bar that crawls to 90% and waits is worse
            // than an honest indeterminate one.
            <div className="h-1 w-full overflow-hidden rounded-full bg-surface-warm">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-amber" />
            </div>
          )}

          <p className="text-[12px] leading-relaxed text-text-muted">
            {stage === 'uploading'
              ? 'Sending your file securely. The file itself is never stored.'
              : 'Reading your file and merging it with your profile. This usually takes under a minute, or a few minutes for a large spreadsheet — nothing is saved until you review it.'}
          </p>
        </div>
      )}

      {footer}
    </div>
  )
}
