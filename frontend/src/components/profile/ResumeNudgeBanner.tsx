import { useState } from 'react'
import { Link } from 'react-router-dom'
import { X } from 'lucide-react'
import useAuth from '../../hooks/useAuth'

const DISMISS_KEY = 'applify-resume-nudge-dismissed'

function readDismissed(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY) === 'true'
  } catch {
    return false
  }
}

/**
 * Persistent nudge for users who skipped onboarding and still have no profile.
 * Dismissal lasts for the browser session only, so it returns on the next
 * visit until a resume is uploaded.
 */
export default function ResumeNudgeBanner() {
  const { hasProfile, skippedOnboarding } = useAuth()
  const [dismissed, setDismissed] = useState(readDismissed)

  if (dismissed || hasProfile !== false || !skippedOnboarding) return null

  function dismiss() {
    try {
      window.sessionStorage.setItem(DISMISS_KEY, 'true')
    } catch {
      // Storage unavailable: the banner simply returns on the next mount.
    }
    setDismissed(true)
  }

  return (
    <div className="flex flex-shrink-0 items-center gap-2 border-b border-amber/30 bg-amber-light px-4 py-2 sm:gap-3 sm:px-6 sm:py-2.5">
      <p className="flex-1 text-[13px] leading-relaxed text-amber-ink">
        Upload your resume to get grounded analysis.{' '}
        <Link
          to="/onboarding"
          className="font-medium underline underline-offset-2"
        >
          Upload now
        </Link>
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss resume reminder"
        className="-mr-2 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-input text-amber-ink/70 hover:text-amber-ink sm:mr-0 sm:h-auto sm:w-auto"
      >
        <X size={15} />
      </button>
    </div>
  )
}
