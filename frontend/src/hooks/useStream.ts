import { useCallback, useRef, useState } from 'react'

export interface UseStreamResult {
  content: string
  isStreaming: boolean
  error: string | null
  start: (url: string, body?: unknown) => void
  stop: () => void
}

/**
 * Handles SSE streaming of AI responses from the backend.
 * TODO(Phase 6): open the connection, append tokens to chatStore, and clean up
 * on unmount or when the user navigates away.
 */
export function useStream(): UseStreamResult {
  const [content] = useState('')
  const [isStreaming] = useState(false)
  const [error] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const start = useCallback((_url: string, _body?: unknown) => {
    // TODO(Phase 6): fetch the SSE endpoint and read the response stream.
  }, [])

  const stop = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
  }, [])

  return { content, isStreaming, error, start, stop }
}

export default useStream
