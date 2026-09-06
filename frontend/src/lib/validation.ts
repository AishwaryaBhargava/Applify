/** Shared client-side form validation used by the auth and job forms. */

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export const PASSWORD_MIN_LENGTH = 8

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim())
}

/** Returns a message when the email is unusable, or null when it is fine. */
export function validateEmail(value: string): string | null {
  if (!value.trim()) return 'Enter your email address.'
  if (!isValidEmail(value)) return 'Enter a valid email address.'
  return null
}

/** Returns a message when the password is unusable, or null when it is fine. */
export function validatePassword(value: string): string | null {
  if (!value) return 'Enter your password.'
  if (value.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`
  }
  return null
}

/**
 * Returns a message when a job posting URL is unusable, or null when it is
 * fine. An empty value is fine: the field is optional everywhere it appears.
 *
 * The rule mirrors `validate_job_url` in backend/app/api/schemas/tracker.py —
 * http(s) only — and exists here so the user is told before the request rather
 * than by a 422 toast after it. `javascript:` is the reason the backend checks
 * the scheme rather than merely the shape: this URL is rendered as a link.
 */
export function validateJobUrl(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  return /^https?:\/\/\S/i.test(trimmed)
    ? null
    : 'The job URL has to start with http:// or https://'
}
