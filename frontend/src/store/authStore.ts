import { create } from 'zustand'
import type { Session, User } from '@supabase/supabase-js'

/**
 * Holds the Supabase session and user object.
 * No persist middleware here — Supabase restores its own session natively.
 * Login / logout / restore logic lands in Phase 3.
 */
export interface AuthState {
  session: Session | null
  user: User | null
  isLoading: boolean
  hasSkippedOnboarding: boolean
  setSession: (session: Session | null) => void
  setLoading: (isLoading: boolean) => void
  setSkippedOnboarding: (skipped: boolean) => void
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signInWithGoogle: () => Promise<void>
  signOut: () => Promise<void>
  restoreSession: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  user: null,
  isLoading: true,
  hasSkippedOnboarding: false,

  setSession: (session) => set({ session, user: session?.user ?? null }),
  setLoading: (isLoading) => set({ isLoading }),
  setSkippedOnboarding: (hasSkippedOnboarding) => set({ hasSkippedOnboarding }),

  // TODO(Phase 3): implement with supabase.auth.signInWithPassword
  signIn: async (_email, _password) => {},
  // TODO(Phase 3): implement with supabase.auth.signUp
  signUp: async (_email, _password) => {},
  // TODO(Phase 3): implement with supabase.auth.signInWithOAuth (google provider)
  signInWithGoogle: async () => {},
  // TODO(Phase 3): implement with supabase.auth.signOut and clear the store
  signOut: async () => {},
  // TODO(Phase 3): implement with supabase.auth.getSession + onAuthStateChange
  restoreSession: async () => {},
}))
