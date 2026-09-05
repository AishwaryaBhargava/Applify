import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/**
 * True only when both env vars are present and the URL parses. When false the
 * client below is still constructed (against an unreachable placeholder) so
 * nothing throws at import time, and the auth store refuses to call it.
 */
export const isSupabaseConfigured = ((): boolean => {
  if (!supabaseUrl || !supabaseAnonKey) return false
  try {
    new URL(supabaseUrl)
    return true
  } catch {
    return false
  }
})()

if (!isSupabaseConfigured) {
  // Fail loudly in development so a missing .env is obvious immediately.
  console.warn(
    '[applify] Missing or invalid VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. ' +
      'Check frontend/.env — authentication is disabled until they are set.',
  )
}

// createClient throws synchronously on an empty URL, which would blank the
// whole app at import time. Fall back to a syntactically valid placeholder:
// every call then fails as a normal network error the store can catch.
const PLACEHOLDER_URL = 'https://placeholder.supabase.co'
const PLACEHOLDER_KEY = 'placeholder-anon-key'

/** Single Supabase client instance used by the auth store and service calls. */
export const supabase = createClient(
  isSupabaseConfigured ? supabaseUrl : PLACEHOLDER_URL,
  isSupabaseConfigured ? supabaseAnonKey : PLACEHOLDER_KEY,
  {
    auth: {
      persistSession: true,
      autoRefreshToken: isSupabaseConfigured,
      detectSessionInUrl: isSupabaseConfigured,
    },
  },
)

/** Message shown wherever an auth action is attempted without configuration. */
export const SUPABASE_NOT_CONFIGURED =
  'Authentication is not configured yet. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env and reload.'

export default supabase
