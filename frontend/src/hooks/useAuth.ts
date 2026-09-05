import type { Session, User } from '@supabase/supabase-js'
import { useAuthStore } from '../store/authStore'
import type { AuthResult, SignUpMetadata } from '../store/authStore'

export interface UseAuthResult {
  session: Session | null
  user: User | null
  isAuthenticated: boolean
  /** Initial session restore in flight. */
  isLoading: boolean
  /** A sign-in / sign-up / sign-out request is in flight. */
  isSubmitting: boolean
  error: string | null
  /** null = not checked yet, true = profile exists, false = none on record. */
  hasProfile: boolean | null
  skippedOnboarding: boolean
  /** First name from signup metadata, else the email, else null. */
  displayName: string | null

  initialize: () => Promise<void>
  signIn: (email: string, password: string) => Promise<AuthResult>
  signUp: (
    email: string,
    password: string,
    metadata: SignUpMetadata,
  ) => Promise<AuthResult>
  signInWithGoogle: () => Promise<AuthResult>
  sendPasswordReset: (email: string) => Promise<AuthResult>
  signOut: () => Promise<void>
  checkProfile: () => Promise<void>
  setSkippedOnboarding: (skipped: boolean) => void
  setHasProfile: (hasProfile: boolean | null) => void
  clearError: () => void
}

/** Reads the auth store and exposes auth status booleans plus its actions. */
export function useAuth(): UseAuthResult {
  const session = useAuthStore((state) => state.session)
  const user = useAuthStore((state) => state.user)
  const isLoading = useAuthStore((state) => state.isLoading)
  const isSubmitting = useAuthStore((state) => state.isSubmitting)
  const error = useAuthStore((state) => state.error)
  const hasProfile = useAuthStore((state) => state.hasProfile)
  const skippedOnboarding = useAuthStore((state) => state.skippedOnboarding)

  const initialize = useAuthStore((state) => state.initialize)
  const signIn = useAuthStore((state) => state.signInWithPassword)
  const signUp = useAuthStore((state) => state.signUp)
  const signInWithGoogle = useAuthStore((state) => state.signInWithGoogle)
  const sendPasswordReset = useAuthStore((state) => state.sendPasswordReset)
  const signOut = useAuthStore((state) => state.signOut)
  const checkProfile = useAuthStore((state) => state.checkProfile)
  const setSkippedOnboarding = useAuthStore(
    (state) => state.setSkippedOnboarding,
  )
  const setHasProfile = useAuthStore((state) => state.setHasProfile)
  const clearError = useAuthStore((state) => state.clearError)

  const metadata = user?.user_metadata as
    | { first_name?: string; full_name?: string; name?: string }
    | undefined
  const displayName =
    metadata?.first_name ||
    metadata?.full_name ||
    metadata?.name ||
    user?.email ||
    null

  return {
    session,
    user,
    isAuthenticated: Boolean(session),
    isLoading,
    isSubmitting,
    error,
    hasProfile,
    skippedOnboarding,
    displayName,
    initialize,
    signIn,
    signUp,
    signInWithGoogle,
    sendPasswordReset,
    signOut,
    checkProfile,
    setSkippedOnboarding,
    setHasProfile,
    clearError,
  }
}

export default useAuth
