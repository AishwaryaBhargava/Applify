import { create } from 'zustand'
import type { Session, User } from '@supabase/supabase-js'
import {
  SUPABASE_NOT_CONFIGURED,
  isSupabaseConfigured,
  supabase,
} from '../lib/supabase'
import { getProfile } from '../services/profile'

const SKIP_KEY = 'applify-skipped-onboarding'

function readSkipped(): boolean {
  try {
    return window.localStorage.getItem(SKIP_KEY) === 'true'
  } catch {
    return false
  }
}

function writeSkipped(skipped: boolean): void {
  try {
    if (skipped) window.localStorage.setItem(SKIP_KEY, 'true')
    else window.localStorage.removeItem(SKIP_KEY)
  } catch {
    // Private mode / storage disabled: skip state lives in memory only.
  }
}

/** Turns any thrown value into a message safe to render in the UI. */
function toMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    // Supabase surfaces a dead or unreachable project as a bare "Failed to
    // fetch" (AuthRetryableFetchError). Translate it into something a user can
    // act on rather than leaking fetch wording.
    const unreachable =
      error.name === 'AuthRetryableFetchError' ||
      /failed to fetch|fetch failed|network|load failed|ERR_NAME_NOT_RESOLVED/i.test(
        error.message,
      )
    if (unreachable) {
      return 'Cannot reach the authentication service. Check your connection or try again shortly.'
    }
    return error.message
  }
  return fallback
}

/** Outcome of a sign-in or sign-up attempt, read by the auth forms. */
export type AuthResult =
  | { ok: true; needsEmailConfirmation?: boolean }
  | { ok: false; error: string }

export interface SignUpMetadata {
  first_name: string
  last_name: string
}

export interface AuthState {
  session: Session | null
  user: User | null
  /** True until the initial Supabase session lookup settles. */
  isLoading: boolean
  /** True while a sign-in / sign-up / sign-out request is in flight. */
  isSubmitting: boolean
  error: string | null
  /** null = not checked yet, true = profile exists, false = none on record. */
  hasProfile: boolean | null
  /** User chose "Skip for now" on onboarding (persisted in localStorage). */
  skippedOnboarding: boolean

  initialize: () => Promise<void>
  signInWithPassword: (email: string, password: string) => Promise<AuthResult>
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
  setError: (error: string | null) => void
  clearError: () => void
}

/** Guards against a second initialize() (React StrictMode mounts twice). */
let initializePromise: Promise<void> | null = null
/** De-dupes concurrent profile checks fired by the route guard. */
let profileCheckPromise: Promise<void> | null = null

export const useAuthStore = create<AuthState>((set, get) => ({
  session: null,
  user: null,
  isLoading: true,
  isSubmitting: false,
  error: null,
  hasProfile: null,
  skippedOnboarding: readSkipped(),

  setSkippedOnboarding: (skipped) => {
    writeSkipped(skipped)
    set({ skippedOnboarding: skipped })
  },
  setHasProfile: (hasProfile) => set({ hasProfile }),
  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),

  /**
   * Restores the persisted Supabase session and subscribes to auth changes.
   * Safe to call more than once - later calls await the first.
   */
  initialize: async () => {
    if (initializePromise) return initializePromise

    initializePromise = (async () => {
      if (!isSupabaseConfigured) {
        set({ isLoading: false, error: SUPABASE_NOT_CONFIGURED })
        return
      }

      try {
        const { data, error } = await supabase.auth.getSession()
        if (error) throw error
        set({
          session: data.session,
          user: data.session?.user ?? null,
          isLoading: false,
        })
      } catch (error) {
        // A dead Supabase project must not blank the app: land as signed out
        // with a readable message instead.
        set({
          session: null,
          user: null,
          isLoading: false,
          error: toMessage(error, 'Could not restore your session.'),
        })
      }

      try {
        supabase.auth.onAuthStateChange((_event, session) => {
          const previousUserId = get().user?.id
          const nextUserId = session?.user?.id
          set({
            session,
            user: session?.user ?? null,
            // A different user (or a sign-out) invalidates the profile check.
            hasProfile: previousUserId === nextUserId ? get().hasProfile : null,
          })
          if (!session) profileCheckPromise = null
        })
      } catch (error) {
        console.warn('[applify] Could not subscribe to auth changes', error)
      }
    })()

    return initializePromise
  },

  signInWithPassword: async (email, password) => {
    if (!isSupabaseConfigured) {
      set({ error: SUPABASE_NOT_CONFIGURED })
      return { ok: false, error: SUPABASE_NOT_CONFIGURED }
    }
    set({ isSubmitting: true, error: null })
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      })
      if (error) throw error
      set({
        session: data.session,
        user: data.user,
        hasProfile: null,
        isSubmitting: false,
      })
      return { ok: true }
    } catch (error) {
      const message = toMessage(error, 'Could not sign in. Please try again.')
      set({ isSubmitting: false, error: message })
      return { ok: false, error: message }
    }
  },

  signUp: async (email, password, metadata) => {
    if (!isSupabaseConfigured) {
      set({ error: SUPABASE_NOT_CONFIGURED })
      return { ok: false, error: SUPABASE_NOT_CONFIGURED }
    }
    set({ isSubmitting: true, error: null })
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            first_name: metadata.first_name,
            last_name: metadata.last_name,
            full_name: `${metadata.first_name} ${metadata.last_name}`.trim(),
          },
          emailRedirectTo: `${window.location.origin}/chat`,
        },
      })
      if (error) throw error
      // No session back means Supabase requires email confirmation first.
      const needsEmailConfirmation = !data.session
      set({
        session: data.session,
        user: data.user,
        hasProfile: null,
        isSubmitting: false,
      })
      return { ok: true, needsEmailConfirmation }
    } catch (error) {
      const message = toMessage(
        error,
        'Could not create your account. Please try again.',
      )
      set({ isSubmitting: false, error: message })
      return { ok: false, error: message }
    }
  },

  signInWithGoogle: async () => {
    if (!isSupabaseConfigured) {
      set({ error: SUPABASE_NOT_CONFIGURED })
      return { ok: false, error: SUPABASE_NOT_CONFIGURED }
    }
    set({ isSubmitting: true, error: null })
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}/chat` },
      })
      if (error) throw error
      // The browser is navigating to Google; keep the button disabled.
      return { ok: true }
    } catch (error) {
      const message = toMessage(
        error,
        'Could not start Google sign-in. Please try again.',
      )
      set({ isSubmitting: false, error: message })
      return { ok: false, error: message }
    }
  },

  sendPasswordReset: async (email) => {
    if (!isSupabaseConfigured) {
      set({ error: SUPABASE_NOT_CONFIGURED })
      return { ok: false, error: SUPABASE_NOT_CONFIGURED }
    }
    set({ isSubmitting: true, error: null })
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/login`,
      })
      if (error) throw error
      set({ isSubmitting: false })
      return { ok: true }
    } catch (error) {
      const message = toMessage(
        error,
        'Could not send the reset email. Please try again.',
      )
      set({ isSubmitting: false, error: message })
      return { ok: false, error: message }
    }
  },

  signOut: async () => {
    set({ isSubmitting: true, error: null })
    try {
      if (isSupabaseConfigured) await supabase.auth.signOut()
    } catch (error) {
      // Even if the network call fails, drop local state - the user asked to
      // leave. Supabase clears its own storage on the next successful call.
      console.warn('[applify] Sign out request failed', error)
    } finally {
      profileCheckPromise = null
      set({
        session: null,
        user: null,
        hasProfile: null,
        isSubmitting: false,
        error: null,
      })
    }
  },

  /**
   * GET /profile to decide whether onboarding is still needed.
   * 404 maps to false. Any other failure also resolves to false so the route
   * guard never spins forever; the message is kept in `error` for the UI.
   */
  checkProfile: async () => {
    if (profileCheckPromise) return profileCheckPromise
    if (!get().session) {
      set({ hasProfile: null })
      return
    }

    profileCheckPromise = (async () => {
      const result = await getProfile()
      if (result.status === 'ok') {
        set({ hasProfile: true })
      } else if (result.status === 'missing') {
        set({ hasProfile: false })
      } else {
        set({ hasProfile: false, error: result.message })
      }
    })().finally(() => {
      profileCheckPromise = null
    })

    return profileCheckPromise
  },
}))

export default useAuthStore
