import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Logo from '../components/common/Logo'
import ProfileImportUpload from '../components/profile/ProfileImportUpload'
import ResumeUpload from '../components/profile/ResumeUpload'
import useAuth from '../hooks/useAuth'

/**
 * Resume upload and initial profile setup. Deliberately rendered outside the
 * app shell: it is a focused, single-purpose first-run page.
 *
 * A resume is the fast path and stays the default. The second option exists
 * because plenty of people keep their history in a spreadsheet and have no
 * current resume at all — asking them to write one before they can try the
 * product is exactly backwards.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const { setSkippedOnboarding, displayName } = useAuth()
  const [showImport, setShowImport] = useState(false)

  function handleSkip() {
    setSkippedOnboarding(true)
    navigate('/chat', { replace: true })
  }

  return (
    <div className="min-h-dvh bg-bg">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-6 px-5 py-8 sm:px-6 sm:py-12">
        <Logo size={34} />

        <div>
          <h1 className="font-serif text-2xl font-medium text-teal-ink">
            {displayName
              ? `Let's build your profile, ${displayName}`
              : "Let's build your profile"}
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">
            Upload your resume once, or bring a spreadsheet or document with your
            history instead. Applify parses either into a persistent profile that
            grounds every analysis and every generated document. The file itself
            is never stored — only the text we extract from it.
          </p>
        </div>

        {showImport ? (
          <>
            <ProfileImportUpload />
            <button
              type="button"
              onClick={() => setShowImport(false)}
              className="mx-auto flex min-h-[44px] items-center justify-center px-4 text-center text-[13px] font-medium text-teal-deep underline-offset-2 hover:underline"
            >
              Upload a resume instead
            </button>
          </>
        ) : (
          <>
            <ResumeUpload />
            <button
              type="button"
              onClick={() => setShowImport(true)}
              className="mx-auto flex min-h-[44px] items-center justify-center px-4 text-center text-[13px] font-medium text-teal-deep underline-offset-2 hover:underline"
            >
              Import a file instead — a spreadsheet or document with your history
            </button>
          </>
        )}

        <button
          type="button"
          onClick={handleSkip}
          className="mx-auto flex min-h-[44px] items-center justify-center px-4 text-center text-[13px] text-text-muted underline-offset-2 hover:text-text-primary hover:underline"
        >
          Skip for now
        </button>
      </div>
    </div>
  )
}
