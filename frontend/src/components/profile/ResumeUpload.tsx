import { useEffect, useRef, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, FileText, UploadCloud, X } from 'lucide-react'
import { uploadResume } from '../../services/profile'
import { apiErrorMessage } from '../../services/api'
import { useProfileStore } from '../../store/profileStore'
import { pushToast } from '../../store/toastStore'
import useAuth from '../../hooks/useAuth'
import Spinner from '../common/Spinner'
import type { Profile } from '../../types'

const MAX_BYTES = 10 * 1024 * 1024
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx']
const ACCEPTED_MIME = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

/** Progress stages shown while the resume is uploaded and parsed. */
type Stage = 'idle' | 'uploading' | 'parsing' | 'saving' | 'done'

const STEPS: { key: Exclude<Stage, 'idle' | 'done'>; label: string }[] = [
  { key: 'uploading', label: 'Uploading' },
  { key: 'parsing', label: 'Parsing' },
  { key: 'saving', label: 'Saving' },
]

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Returns a rejection message, or null when the file is acceptable. */
function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  const hasValidExtension = ACCEPTED_EXTENSIONS.some((ext) =>
    name.endsWith(ext),
  )
  const hasValidMime = ACCEPTED_MIME.includes(file.type)
  if (!hasValidExtension && !hasValidMime) {
    return 'That file type is not supported. Upload a PDF or DOCX resume.'
  }
  if (file.size > MAX_BYTES) {
    return `That file is ${formatSize(file.size)}. The limit is 10MB.`
  }
  if (file.size === 0) return 'That file is empty. Try a different resume.'
  return null
}

interface ResumeUploadProps {
  onFileSelected?: (file: File) => void
  onUploaded?: (profile: Profile) => void
  /** Where to go after a successful parse. */
  redirectTo?: string
}

/**
 * Drag-and-drop or file picker for resume upload (PDF / DOCX, max 10MB).
 * Uploads to POST /profile/upload, shows Uploading -> Parsing -> Saving, then
 * stores the parsed profile and moves the user on to review it.
 */
export default function ResumeUpload({
  onFileSelected,
  onUploaded,
  redirectTo = '/profile',
}: ResumeUploadProps) {
  const navigate = useNavigate()
  const setProfile = useProfileStore((state) => state.setProfile)
  const setGaps = useProfileStore((state) => state.setGaps)
  const resetDismissals = useProfileStore((state) => state.resetDismissals)
  const { setHasProfile } = useAuth()

  const inputRef = useRef<HTMLInputElement>(null)
  const parsingTimerRef = useRef<number | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [progress, setProgress] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  const isBusy = stage !== 'idle' && stage !== 'done'

  useEffect(
    () => () => {
      if (parsingTimerRef.current) window.clearTimeout(parsingTimerRef.current)
    },
    [],
  )

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
    onFileSelected?.(candidate)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragging(false)
    if (isBusy) return
    acceptFile(event.dataTransfer.files?.[0])
  }

  function clearSelection() {
    setFile(null)
    setError(null)
    setProgress(0)
    setStage('idle')
    if (inputRef.current) inputRef.current.value = ''
  }

  async function handleUpload() {
    if (!file || isBusy) return

    setError(null)
    setProgress(0)
    setStage('uploading')

    // Small resumes can finish uploading before any progress event lands, so
    // guarantee the Parsing step becomes visible either way.
    parsingTimerRef.current = window.setTimeout(() => {
      setStage((current) => (current === 'uploading' ? 'parsing' : current))
    }, 900)

    try {
      const profile = await uploadResume(file, (event) => {
        if (!event.total) return
        const percent = Math.round((event.loaded / event.total) * 100)
        setProgress(percent)
        if (percent >= 100) {
          // Bytes are on the wire: the server is parsing from here on.
          setStage((current) => (current === 'uploading' ? 'parsing' : current))
        }
      })

      setStage('saving')
      // Seed the store so /profile renders the parsed sections immediately;
      // its own fetch then confirms them without a skeleton flash.
      setProfile(profile)
      // A new resume is a new profile: the old nudges no longer describe it,
      // and every dismissal earned against the old one is spent.
      setGaps([])
      resetDismissals()
      setHasProfile(true)
      onUploaded?.(profile)
      setStage('done')
      navigate(redirectTo, { replace: true })
    } catch (uploadError) {
      const message = apiErrorMessage(
        uploadError,
        'We could not parse that resume. Please try again.',
      )
      setStage('idle')
      setProgress(0)
      // Inline under the dropzone, where the Upload button still is, plus a
      // toast so a failure after a long parse is not missed.
      setError(message)
      pushToast(message, 'error')
    } finally {
      if (parsingTimerRef.current) {
        window.clearTimeout(parsingTimerRef.current)
        parsingTimerRef.current = null
      }
    }
  }

  const activeStepIndex = STEPS.findIndex((step) => step.key === stage)

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          if (!isBusy) setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`rounded-card border border-dashed bg-card px-6 py-10 text-center transition-colors ${
          isDragging
            ? 'border-teal-medium bg-teal-light'
            : 'border-border-input'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
              onClick={handleUpload}
              disabled={isBusy}
              className="flex items-center justify-center gap-2 rounded-btn bg-coral px-5 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-60"
            >
              {isBusy && <Spinner size={14} className="text-white" />}
              {isBusy ? 'Working...' : 'Upload resume'}
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
            <UploadCloud size={24} className="text-teal-deep" />
            <span className="text-[14px] font-medium text-text-primary">
              Drop your resume here
            </span>
            <span className="text-[12px] text-text-muted">
              PDF or DOCX, up to 10MB
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
          <ol className="flex items-center justify-between gap-2">
            {STEPS.map((step, index) => {
              const isComplete = index < activeStepIndex
              const isActive = index === activeStepIndex
              return (
                <li key={step.key} className="flex flex-1 items-center gap-2">
                  <span
                    className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-medium ${
                      isComplete
                        ? 'bg-amber text-white'
                        : isActive
                          ? 'bg-amber text-white'
                          : 'bg-amber-light text-amber-ink'
                    }`}
                  >
                    {isComplete ? <Check size={13} /> : index + 1}
                  </span>
                  <span
                    className={`text-[12px] ${
                      isActive || isComplete
                        ? 'font-medium text-text-primary'
                        : 'text-text-muted'
                    }`}
                  >
                    {step.label}
                  </span>
                  {index < STEPS.length - 1 && (
                    <span className="ml-1 hidden h-px flex-1 bg-border sm:block" />
                  )}
                </li>
              )
            })}
          </ol>

          {stage === 'uploading' && (
            <div className="h-1 w-full overflow-hidden rounded-full bg-surface-warm">
              <div
                className="h-full rounded-full bg-amber transition-[width] duration-200"
                style={{ width: `${Math.max(progress, 4)}%` }}
              />
            </div>
          )}

          <p className="text-[12px] text-text-muted">
            {stage === 'uploading'
              ? 'Sending your resume securely. The file itself is never stored.'
              : stage === 'parsing'
                ? 'Reading your experience, education, skills and projects.'
                : 'Saving your profile.'}
          </p>
        </div>
      )}
    </div>
  )
}
