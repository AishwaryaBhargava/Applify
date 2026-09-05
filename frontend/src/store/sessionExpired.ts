import { navigateTo } from '../lib/navigation'
import { useAuthStore } from './authStore'
import { endSession } from './session'
import { pushToast } from './toastStore'

/** Guards against a burst of 401s producing a burst of sign-outs and toasts. */
let handling = false

/**
 * A 401 from the API after the session existed: the access token expired (or
 * was revoked) and every request from here on would fail the same way.
 *
 * Signs the user out, says why, and sends them to /login. A 401 raised while
 * there was never a session is ignored: that is a request that raced the
 * initial session restore, not an expiry, and bouncing the user for it would
 * interrupt a sign-in that is still working.
 *
 * Lives apart from `endSession` so that it is only ever reached through a
 * dynamic import — the request layer cannot import the stores at module scope
 * without closing a cycle back through `services/api`.
 */
export async function handleSessionExpired(): Promise<void> {
  if (handling) return
  if (!useAuthStore.getState().session) return

  handling = true
  try {
    await endSession()
    pushToast('Your session expired', 'error')
    navigateTo('/login', { replace: true })
  } finally {
    handling = false
  }
}
