import { useEffect } from 'react'

/**
 * Warns before the browser throws an unsaved draft away.
 *
 * Only covers leaving the *document* — a reload, a closed tab, a typed URL.
 * Navigation inside the app never fires `beforeunload`, so it is guarded
 * separately by `useNavigationGuard`, which can show a real dialog instead of
 * the browser's fixed one.
 *
 * The listener is attached only while something is actually dirty: a page that
 * registers `beforeunload` unconditionally opts itself out of the back-forward
 * cache for no reason.
 *
 * @param isDirty Whether there is anything worth stopping for.
 */
export function useUnsavedChanges(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      // Browsers show their own wording and ignore ours; both of these are
      // needed for every engine to show it at all.
      event.preventDefault()
      event.returnValue = ''
      return ''
    }

    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [isDirty])
}

export default useUnsavedChanges
