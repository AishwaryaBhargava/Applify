import { useCallback, useEffect, useRef, type MutableRefObject } from 'react'

/** How close to the bottom still counts as "following the conversation". */
const STICK_THRESHOLD_PX = 80

export interface UseAutoScrollResult<T extends HTMLElement> {
  ref: MutableRefObject<T | null>
  /** Jumps to the bottom and re-arms following, for a "jump to latest" button. */
  scrollToBottom: () => void
}

/**
 * Keeps a scrollable container pinned to the bottom as content arrives, but
 * only while the user is already there.
 *
 * Scrolling up during a stream is a deliberate act — the user is reading
 * something further back — so following switches off until they return to
 * within `STICK_THRESHOLD_PX` of the bottom, at which point it resumes.
 */
export function useAutoScroll<T extends HTMLElement = HTMLDivElement>(
  deps: unknown[] = [],
): UseAutoScrollResult<T> {
  const ref = useRef<T | null>(null)
  const following = useRef(true)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const onScroll = () => {
      const distance = node.scrollHeight - node.scrollTop - node.clientHeight
      following.current = distance <= STICK_THRESHOLD_PX
    }

    node.addEventListener('scroll', onScroll, { passive: true })
    return () => node.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const node = ref.current
    if (!node || !following.current) return
    node.scrollTop = node.scrollHeight
    // The caller decides what "new content" means (message count, streamed
    // length); this effect only reacts to it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  const scrollToBottom = useCallback(() => {
    const node = ref.current
    if (!node) return
    following.current = true
    node.scrollTop = node.scrollHeight
  }, [])

  return { ref, scrollToBottom }
}

export default useAutoScroll
