import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import SignupForm from '../components/auth/SignupForm'
import GoogleButton from '../components/auth/GoogleButton'
import AuthPitchPanel from '../components/auth/AuthPitchPanel'
import useAuth from '../hooks/useAuth'

/** Signup page: deep teal pitch panel + account creation and Google sign-in. */
export default function Signup() {
  const { clearError } = useAuth()

  // Errors from a previous attempt should not greet the next visit.
  useEffect(() => clearError, [clearError])

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg p-4 sm:p-6">
      <div className="grid w-full max-w-3xl overflow-hidden rounded-panel border border-border bg-card md:grid-cols-[220px_1fr]">
        <AuthPitchPanel />

        <div className="bg-card p-6 sm:p-8">
          <h1 className="font-serif text-xl font-medium text-teal-ink">
            Get started
          </h1>
          <p className="mb-6 mt-1 text-[13px] text-text-muted">
            Create your free Applify account
          </p>
          <SignupForm />
          <div className="my-4 flex items-center gap-2.5">
            <span className="h-px flex-1 bg-border" />
            <span className="text-[12px] text-text-muted">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <GoogleButton />
          <p className="mt-4 text-center text-[13px] text-text-muted">
            Already have an account?{' '}
            <Link to="/login" className="inline-flex min-h-[40px] items-center font-medium text-teal-deep underline-offset-2 hover:underline sm:min-h-0">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
