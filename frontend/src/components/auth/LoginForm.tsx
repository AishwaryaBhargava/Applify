import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../../hooks/useAuth'
import { validateEmail, validatePassword } from '../../lib/validation'
import AuthMessage from './AuthMessage'
import Spinner from '../common/Spinner'

const inputClass =
  'w-full min-h-[44px] rounded-input border border-border-input bg-bg px-3 py-2.5 text-[16px] outline-none focus:border-teal-deep disabled:opacity-60 sm:min-h-0 sm:text-[13px]'

/** Email + password login form, wired to the auth store. */
export default function LoginForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn, sendPasswordReset, isSubmitting, error, clearError } =
    useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string
    password?: string
  }>({})
  const [notice, setNotice] = useState<string | null>(null)

  const redirectTo =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? '/chat'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice(null)
    clearError()

    const nextErrors = {
      email: validateEmail(email) ?? undefined,
      password: validatePassword(password) ?? undefined,
    }
    setFieldErrors(nextErrors)
    if (nextErrors.email || nextErrors.password) return

    const result = await signIn(email.trim(), password)
    if (result.ok) {
      // The route guard bounces to /onboarding if there is no profile yet.
      navigate(redirectTo, { replace: true })
    }
  }

  async function handleForgotPassword() {
    setNotice(null)
    clearError()

    const emailError = validateEmail(email)
    if (emailError) {
      setFieldErrors((prev) => ({
        ...prev,
        email: 'Enter your email above, then click "Forgot password?" again.',
      }))
      return
    }

    const result = await sendPasswordReset(email.trim())
    if (result.ok) {
      setNotice(
        `If an account exists for ${email.trim()}, a password reset link is on its way.`,
      )
    }
  }

  return (
    <form className="flex flex-col gap-3.5" onSubmit={handleSubmit} noValidate>
      {error && <AuthMessage message={error} tone="error" />}
      {notice && <AuthMessage message={notice} tone="success" />}

      <div>
        <label
          className="mb-1.5 block text-[12px] font-medium text-text-primary"
          htmlFor="login-email"
        >
          Email
        </label>
        <input
          id="login-email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@email.com"
          className={inputClass}
          value={email}
          disabled={isSubmitting}
          onChange={(event) => {
            setEmail(event.target.value)
            if (fieldErrors.email) {
              setFieldErrors((prev) => ({ ...prev, email: undefined }))
            }
          }}
          aria-invalid={Boolean(fieldErrors.email)}
        />
        {fieldErrors.email && (
          <p className="mt-1 text-[12px] leading-relaxed text-coral-ink sm:text-[11px]">{fieldErrors.email}</p>
        )}
      </div>

      <div>
        <label
          className="mb-1.5 block text-[12px] font-medium text-text-primary"
          htmlFor="login-password"
        >
          Password
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          placeholder="********"
          className={inputClass}
          value={password}
          disabled={isSubmitting}
          onChange={(event) => {
            setPassword(event.target.value)
            if (fieldErrors.password) {
              setFieldErrors((prev) => ({ ...prev, password: undefined }))
            }
          }}
          aria-invalid={Boolean(fieldErrors.password)}
        />
        {fieldErrors.password && (
          <p className="mt-1 text-[12px] leading-relaxed text-coral-ink sm:text-[11px]">
            {fieldErrors.password}
          </p>
        )}
      </div>

      <div className="-mt-1 text-right">
        <button
          type="button"
          onClick={handleForgotPassword}
          disabled={isSubmitting}
          className="inline-flex min-h-[40px] items-center text-[12px] text-teal-deep underline-offset-2 hover:underline disabled:opacity-60 sm:min-h-0"
        >
          Forgot password?
        </button>
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="mt-1 flex min-h-[46px] w-full items-center justify-center gap-2 rounded-btn bg-coral px-4 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-60"
      >
        {isSubmitting && <Spinner size={14} className="text-white" />}
        {isSubmitting ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
  )
}
