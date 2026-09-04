import { Link } from 'react-router-dom'
import Logo from '../components/common/Logo'
import ResumeUpload from '../components/profile/ResumeUpload'

/**
 * Resume upload and initial profile setup.
 * TODO(Phase 4): upload via POST /profile/upload with progress states.
 */
export default function Onboarding() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6 px-6 py-12">
      <Logo size={34} />
      <div>
        <h1 className="font-serif text-2xl font-medium text-teal-ink">
          Let&apos;s build your profile
        </h1>
        <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">
          Upload your resume once. Applify parses it into a persistent profile
          that grounds every analysis and every generated document.
        </p>
      </div>
      <ResumeUpload />
      <Link to="/chat" className="text-center text-[13px] text-text-muted">
        Skip for now
      </Link>
    </div>
  )
}
