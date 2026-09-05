import { useNavigate } from 'react-router-dom'
import Logo from '../components/common/Logo'
import ResumeUpload from '../components/profile/ResumeUpload'
import useAuth from '../hooks/useAuth'

/**
 * Resume upload and initial profile setup. Deliberately rendered outside the
 * app shell: it is a focused, single-purpose first-run page.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const { setSkippedOnboarding, displayName } = useAuth()

  function handleSkip() {
    setSkippedOnboarding(true)
    navigate('/chat', { replace: true })
  }

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-6 px-6 py-12">
        <Logo size={34} />

        <div>
          <h1 className="font-serif text-2xl font-medium text-teal-ink">
            {displayName
              ? `Let's build your profile, ${displayName}`
              : "Let's build your profile"}
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">
            Upload your resume once. Applify parses it into a persistent profile
            that grounds every analysis and every generated document. The file
            itself is never stored — only the text we extract from it.
          </p>
        </div>

        <ResumeUpload />

        <button
          type="button"
          onClick={handleSkip}
          className="text-center text-[13px] text-text-muted underline-offset-2 hover:text-text-primary hover:underline"
        >
          Skip for now
        </button>
      </div>
    </div>
  )
}
