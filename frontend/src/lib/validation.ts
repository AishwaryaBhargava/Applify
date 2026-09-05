/** Shared client-side form validation used by the auth forms. */

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
