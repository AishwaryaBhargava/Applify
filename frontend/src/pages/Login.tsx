import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import LoginForm from '../components/auth/LoginForm'
import GoogleButton from '../components/auth/GoogleButton'
import AuthPitchPanel from '../components/auth/AuthPitchPanel'
import useAuth from '../hooks/useAuth'

/** Login page: deep teal pitch panel + email/password and Google sign-in. */
export default function Login() {
  const { clearError } = useAuth()

  // Errors from a previous attempt should not greet the next visit.
  useEffect(() => clearError, [clearError])

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <div className="grid w-full max-w-3xl overflow-hidden rounded-panel border border-border bg-card md:grid-cols-[220px_1fr]">
        <AuthPitchPanel />

        <div className="bg-card p-8">
          <h1 className="font-serif text-xl font-medium text-teal-ink">
            Welcome back
          </h1>
          <p className="mb-6 mt-1 text-[13px] text-text-muted">
            Sign in to your Applify account
          </p>
          <LoginForm />
          <div className="my-4 flex items-center gap-2.5">
            <span className="h-px flex-1 bg-border" />
            <span className="text-[12px] text-text-muted">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <GoogleButton />
          <p className="mt-4 text-center text-[12px] text-text-muted">
            Don&apos;t have an account?{' '}
            <Link to="/signup" className="font-medium text-teal-deep">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
