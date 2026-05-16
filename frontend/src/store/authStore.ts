import { create } from 'zustand'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

interface AuthState {
  session: Session | null
  user: User | null
  loading: boolean
  setSession: (session: Session | null) => void
  logout: () => Promise<void>
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  user: null,
  loading: true,

  setSession: (session) => set({
    session,
    user: session?.user ?? null,
    loading: false
  }),

  logout: async () => {
    await supabase.auth.signOut()
    set({ session: null, user: null })
  },

  initialize: async () => {
    const { data } = await supabase.auth.getSession()
    set({
      session: data.session,
      user: data.session?.user ?? null,
      loading: false
    })

    supabase.auth.onAuthStateChange((_event, session) => {
      set({
        session,
        user: session?.user ?? null,
        loading: false
      })
    })
  }
}))