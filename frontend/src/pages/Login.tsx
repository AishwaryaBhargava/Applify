import { Link } from 'react-router-dom'
import LoginForm from '../components/auth/LoginForm'
import GoogleButton from '../components/auth/GoogleButton'
import Logo from '../components/common/Logo'

/**
 * Login page shell.
 * TODO(Phase 3): wire the form to authStore and redirect on success.
 */
export default function Login() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <div className="grid w-full max-w-3xl overflow-hidden rounded-panel border border-border md:grid-cols-[220px_1fr]">
        <div className="hidden flex-col justify-between bg-teal-deep p-8 md:flex">
          <Logo size={32} variant="light" />
          <div>
            <h2 className="font-serif text-[22px] font-medium leading-snug text-white">
              Your applications,
              <br />
              <span className="text-[#FAC775]">finally organized.</span>
            </h2>
            <p className="mt-3 text-[13px] leading-relaxed text-teal-soft">
              One workspace for every job you apply to.
            </p>
          </div>
          <p className="text-[11px] text-teal-soft">
            Free during beta. No credit card required.
          </p>
        </div>

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
