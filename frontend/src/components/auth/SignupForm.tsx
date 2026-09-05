import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../../hooks/useAuth'
import {
  PASSWORD_MIN_LENGTH,
  validateEmail,
  validatePassword,
} from '../../lib/validation'
import AuthMessage from './AuthMessage'
import Spinner from '../common/Spinner'

const inputClass =
  'w-full min-h-[44px] rounded-input border border-border-input bg-bg px-3 py-2.5 text-[16px] outline-none focus:border-teal-deep disabled:opacity-60 sm:min-h-0 sm:text-[13px]'

interface FieldErrors {
  firstName?: string
  lastName?: string
  email?: string
  password?: string
}

/** Email + password signup form, wired to the auth store. */
export default function SignupForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signUp, isSubmitting, error, clearError } = useAuth()

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [confirmationNotice, setConfirmationNotice] = useState<string | null>(
    null,
  )

  const redirectTo =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? '/chat'

  function clearField(field: keyof FieldErrors) {
    setFieldErrors((prev) =>
      prev[field] ? { ...prev, [field]: undefined } : prev,
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setConfirmationNotice(null)
    clearError()

    const nextErrors: FieldErrors = {
      firstName: firstName.trim() ? undefined : 'Enter your first name.',
      lastName: lastName.trim() ? undefined : 'Enter your last name.',
      email: validateEmail(email) ?? undefined,
      password: validatePassword(password) ?? undefined,
    }
    setFieldErrors(nextErrors)
    if (Object.values(nextErrors).some(Boolean)) return

    const result = await signUp(email.trim(), password, {
      first_name: firstName.trim(),
      last_name: lastName.trim(),
    })

    if (!result.ok) return

    if (result.needsEmailConfirmation) {
      // Supabase created the user but withheld a session until the address is
      // verified, so there is nowhere to redirect to yet.
      setConfirmationNotice(
        `Check your email to confirm your account. We sent a confirmation link to ${email.trim()}.`,
      )
      return
    }

    // The route guard sends a brand new user on to /onboarding.
    navigate(redirectTo, { replace: true })
  }

  if (confirmationNotice) {
    return (
      <div className="flex flex-col gap-3">
        <AuthMessage message={confirmationNotice} tone="success" />
        <p className="text-[12px] leading-relaxed text-text-muted">
          Once confirmed, sign in and Applify will walk you through uploading
          your resume.
        </p>
      </div>
    )
  }

  return (
    <form className="flex flex-col gap-3.5" onSubmit={handleSubmit} noValidate>
      {error && <AuthMessage message={error} tone="error" />}

      <div className="grid grid-cols-1 gap-2.5 xs:grid-cols-2">
        <div>
          <label
            className="mb-1.5 block text-[12px] font-medium text-text-primary"
            htmlFor="signup-first-name"
          >
            First name
          </label>
          <input
            id="signup-first-name"
            name="given-name"
            autoComplete="given-name"
            className={inputClass}
            placeholder="First"
            value={firstName}
            disabled={isSubmitting}
            onChange={(event) => {
              setFirstName(event.target.value)
              clearField('firstName')
            }}
            aria-invalid={Boolean(fieldErrors.firstName)}
          />
          {fieldErrors.firstName && (
            <p className="mt-1 text-[12px] leading-relaxed text-coral-ink sm:text-[11px]">
              {fieldErrors.firstName}
            </p>
          )}
        </div>
        <div>
          <label
            className="mb-1.5 block text-[12px] font-medium text-text-primary"
            htmlFor="signup-last-name"
          >
            Last name
          </label>
          <input
            id="signup-last-name"
            name="family-name"
            autoComplete="family-name"
            className={inputClass}
            placeholder="Last"
            value={lastName}
            disabled={isSubmitting}
            onChange={(event) => {
              setLastName(event.target.value)
              clearField('lastName')
            }}
            aria-invalid={Boolean(fieldErrors.lastName)}
          />
          {fieldErrors.lastName && (
            <p className="mt-1 text-[12px] leading-relaxed text-coral-ink sm:text-[11px]">
              {fieldErrors.lastName}
            </p>
          )}
        </div>
      </div>

      <div>
        <label
          className="mb-1.5 block text-[12px] font-medium text-text-primary"
          htmlFor="signup-email"
        >
          Email
        </label>
        <input
          id="signup-email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@email.com"
          className={inputClass}
          value={email}
          disabled={isSubmitting}
          onChange={(event) => {
            setEmail(event.target.value)
            clearField('email')
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
          htmlFor="signup-password"
        >
          Password
        </label>
        <input
          id="signup-password"
          name="new-password"
          type="password"
          autoComplete="new-password"
          placeholder="********"
          className={inputClass}
          value={password}
          disabled={isSubmitting}
          onChange={(event) => {
            setPassword(event.target.value)
            clearField('password')
          }}
          aria-invalid={Boolean(fieldErrors.password)}
        />
        {fieldErrors.password ? (
          <p className="mt-1 text-[12px] leading-relaxed text-coral-ink sm:text-[11px]">
            {fieldErrors.password}
          </p>
        ) : (
          <p className="mt-1 text-[12px] text-text-muted sm:text-[11px]">
            At least {PASSWORD_MIN_LENGTH} characters.
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="mt-1 flex min-h-[46px] w-full items-center justify-center gap-2 rounded-btn bg-coral px-4 py-2.5 text-[14px] font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-60"
      >
        {isSubmitting && <Spinner size={14} className="text-white" />}
        {isSubmitting ? 'Creating account...' : 'Create account'}
      </button>
    </form>
  )
}
