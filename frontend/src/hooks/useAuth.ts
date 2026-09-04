import { useAuthStore } from '../store/authStore'

export interface UseAuthResult {
  session: ReturnType<typeof useAuthStore.getState>['session']
  user: ReturnType<typeof useAuthStore.getState>['user']
  isAuthenticated: boolean
  isLoading: boolean
}

/**
 * Reads the auth store and exposes auth status booleans.
 * TODO(Phase 3): add redirect helpers and session restore on mount.
 */
export function useAuth(): UseAuthResult {
  const session = useAuthStore((state) => state.session)
  const user = useAuthStore((state) => state.user)
  const isLoading = useAuthStore((state) => state.isLoading)

  return {
    session,
    user,
    isAuthenticated: Boolean(session),
    isLoading,
  }
}

export default useAuth
