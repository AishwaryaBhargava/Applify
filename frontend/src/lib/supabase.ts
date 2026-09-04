import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loudly in development so a missing .env is obvious immediately.
  console.warn(
    '[applify] Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Check frontend/.env',
  )
}

/** Single Supabase client instance used by the auth store and service calls. */
export const supabase = createClient(supabaseUrl ?? '', supabaseAnonKey ?? '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
