import { useCallback, useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { hasUnsavedProfileChanges, useProfileStore } from '../store/profileStore'

/** Copy for the dialog every guarded link puts up. */
export const UNSAVED_TITLE = 'You have unsaved profile changes'
export const UNSAVED_DESCRIPTION =
  'Leaving this page will discard the sections you have edited but not saved.'
export const UNSAVED_LEAVE_LABEL = 'Leave'
export const UNSAVED_STAY_LABEL = 'Stay'

export interface NavigationGuard {
  /** The path a click asked for and the dialog is holding, or null. */
  pendingPath: string | null
  /**
   * Click handler for a `Link` / `NavLink`. Lets the click through untouched
   * when there is nothing to lose, and swallows it into the dialog when there
   * is.
   */
  guardClick: (event: MouseEvent<HTMLElement>, to: string) => void
  /** Cancels the navigation and keeps the drafts. */
  stay: () => void
  /** Goes anyway, dropping the drafts. */
  leave: () => void
}

/**
 * The in-app half of the unsaved-changes guard.
 *
 * React Router 6.28 only offers `useBlocker` under a data router and this app
 * is on `BrowserRouter`, so the guard is at the link instead of at the router:
 * every navigation into the app shell goes through a `NavItem` or a chat row,
 * and both of those ask this hook first. The trade is that a guarded link has
 * to opt in — which is why the check lives in one hook rather than being
 * copy-pasted — and the gain is that no router migration is needed to stop
 * someone losing a half-written role.
 *
 * The dirty flags themselves live in `profileStore`, written by each section
 * editor, so this can run from the sidebar with no access to the page.
 */
export function useNavigationGuard(): NavigationGuard {
  const navigate = useNavigate()
  const clearDirtySections = useProfileStore((state) => state.clearDirtySections)
  const [pendingPath, setPendingPath] = useState<string | null>(null)

  const guardClick = useCallback(
    (event: MouseEvent<HTMLElement>, to: string) => {
      // A modifier click opens a new tab and leaves this one — and its drafts
      // — exactly where they are, so there is nothing to warn about.
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return
      }
      if (!hasUnsavedProfileChanges()) return
      event.preventDefault()
      setPendingPath(to)
    },
    [],
  )

  const stay = useCallback(() => setPendingPath(null), [])

  const leave = useCallback(() => {
    const target = pendingPath
    setPendingPath(null)
    if (!target) return
    // Drop the flags before navigating: the page is about to unmount and its
    // editors would otherwise clear them one render too late, leaving a second
    // guarded click looking at a stale "dirty".
    clearDirtySections()
    navigate(target)
  }, [pendingPath, navigate, clearDirtySections])

  return { pendingPath, guardClick, stay, leave }
}

export default useNavigationGuard
