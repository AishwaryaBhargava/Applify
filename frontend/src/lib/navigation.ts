/**
 * A router handle for code that runs outside React.
 *
 * The Axios interceptor has to send an expired session to /login, but it is not
 * a component and cannot call `useNavigate`. The app shell registers the real
 * navigate function once on mount; anything before that (or after an unmount)
 * falls back to a hard location change, which is correct if slower.
 */
type Navigate = (path: string, options?: { replace?: boolean }) => void

let navigate: Navigate | null = null

/** Called once by the app shell with react-router's navigate. */
export function setNavigator(fn: Navigate | null): void {
  navigate = fn
}

/** Navigates from outside React, falling back to a full page load. */
export function navigateTo(path: string, options?: { replace?: boolean }): void {
  if (navigate) {
    navigate(path, options)
    return
  }
  if (typeof window !== 'undefined') window.location.assign(path)
}
