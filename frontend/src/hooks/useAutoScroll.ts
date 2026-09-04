import { useEffect, useRef } from 'react'

/**
 * Keeps a scrollable container pinned to the bottom as new content arrives.
 * TODO(Phase 6): respect manual scroll-up so streaming does not yank the view.
 */
export function useAutoScroll<T extends HTMLElement = HTMLDivElement>(
  deps: unknown[] = [],
) {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    node.scrollTop = node.scrollHeight
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return ref
}

export default useAutoScroll
