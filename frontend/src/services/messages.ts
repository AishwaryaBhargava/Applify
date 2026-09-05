import api, { RATE_LIMITED_MESSAGE } from './api'
import { supabase } from '../lib/supabase'
import type {
  ChatMessage,
  StreamDoneEvent,
  StreamErrorEvent,
  StreamEvent,
  StreamStartEvent,
} from '../types'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** Absolute URL of the SSE endpoint consumed by `streamMessage`. */
export function messageStreamUrl(chatId: string): string {
  return `${baseURL}/chats/${chatId}/messages`
}

/** GET /chats/{id}/messages — full message history, oldest first. */
export async function listMessages(chatId: string): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>(`/chats/${chatId}/messages`)
  return data
}

export interface StreamHandlers {
  onStart?: (event: StreamStartEvent) => void
  onToken?: (text: string) => void
  onDone?: (event: StreamDoneEvent) => void
  /** Called once for a stream that failed, was rejected, or dropped. */
  onError?: (event: StreamErrorEvent) => void
}

/** Frames are separated by a blank line; CRLF is tolerated. */
const FRAME_SEPARATOR = /\r?\n\r?\n/

/** Current Supabase access token, or null when there is no session. */
async function accessToken(): Promise<string | null> {
  try {
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  } catch {
    // Supabase unreachable: send the request unauthenticated and let the
    // backend answer 401, exactly as the Axios interceptor does.
    return null
  }
}

/**
 * Parses one SSE frame into an event, or null if there is nothing to act on.
 *
 * A frame is a block of lines. Only `data:` lines carry payload; comments
 * (`:heartbeat`) and any `event:` / `id:` fields are ignored, and multiple
 * `data:` lines in one frame are joined with newlines per the SSE spec. The
 * backend sends one JSON object per frame on a single `data:` line — newlines
 * inside token text arrive escaped by `json.dumps`, so they never split a
 * frame — but the multi-line join keeps this correct if that ever changes.
 */
function parseFrame(raw: string): StreamEvent | null {
  const payload = raw
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).replace(/^ /, ''))
    .join('\n')

  if (!payload || payload === '[DONE]') return null

  try {
    const parsed: unknown = JSON.parse(payload)
    if (parsed && typeof parsed === 'object' && 'type' in parsed) {
      return parsed as StreamEvent
    }
  } catch {
    // A truncated or non-JSON frame is dropped rather than killing the stream.
  }
  return null
}

/** Anything the model providers report as "slow down", in the SSE path. */
const RATE_LIMIT_PATTERN =
  /rate.?limit|too many requests|quota|capacity|overloaded|try again later/i

/**
 * The message to show for a rejected stream.
 *
 * The SSE endpoints do not go through Axios, so the mapping services/api does
 * for ordinary requests — rate limits into one sentence, an expired session
 * into a sign-out — has to be repeated here against the raw Response.
 */
async function rejectionMessage(response: Response): Promise<string> {
  let detail = ''
  try {
    const body: unknown = await response.json()
    const raw = (body as { detail?: unknown } | null)?.detail
    if (typeof raw === 'string') detail = raw
  } catch {
    // Empty or non-JSON body: fall through to the status-based message.
  }

  if (response.status === 401) {
    // The token expired mid-session; the app shell signs the user out.
    void import('../store/sessionExpired').then(({ handleSessionExpired }) =>
      handleSessionExpired(),
    )
    return 'Your session expired. Sign in again to pick this up.'
  }

  const rateLimited =
    response.status === 429 ||
    ((response.status === 502 || response.status === 503) &&
      RATE_LIMIT_PATTERN.test(detail))
  if (rateLimited) return RATE_LIMITED_MESSAGE

  if (detail.trim()) return detail
  if (response.status >= 500) {
    return 'The Applify server hit an error. Please try again in a moment.'
  }
  return `The server could not answer that (${response.status}).`
}

/**
 * POST a JSON body to an Applify SSE endpoint and consume the reply.
 *
 * `EventSource` cannot be used here: it is GET-only and cannot carry an
 * Authorization header. So this posts with `fetch`, reads `response.body` with
 * a `ReadableStream` reader, and splits SSE frames by hand.
 *
 * Shared by both streaming endpoints. `POST /chats/{id}/messages` and
 * `POST /chats/{id}/outputs` emit byte-identical frames — the backend reuses
 * one generator for both — so the transport has exactly one definition here
 * and the callers differ only in the URL and the body they post.
 *
 * Resolves when the stream ends. It never rejects: a rejected request, a
 * transport failure mid-stream, and an abort all arrive through `onError`, so
 * a caller has exactly one failure path to handle.
 */
export async function streamSSE(
  url: string,
  body: unknown,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<void> {
  const token = await accessToken()

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    handlers.onError?.({
      type: 'error',
      message:
        (error as Error)?.name === 'AbortError'
          ? 'Stopped.'
          : 'Cannot reach the Applify server. Check your connection and try again.',
    })
    return
  }

  if (!response.ok) {
    handlers.onError?.({
      type: 'error',
      message: await rejectionMessage(response),
    })
    return
  }

  if (!response.body) {
    handlers.onError?.({
      type: 'error',
      message: 'This browser cannot read streamed responses.',
    })
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  /** Drains every complete frame currently in the buffer. */
  const drain = () => {
    let match = FRAME_SEPARATOR.exec(buffer)
    while (match !== null) {
      const frame = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      const event = parseFrame(frame)
      if (event) dispatch(event, handlers)
      match = FRAME_SEPARATOR.exec(buffer)
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      drain()
    }
    // Flush any bytes the decoder was holding, then any frame the server sent
    // without a trailing blank line.
    buffer += decoder.decode()
    drain()
    const tail = parseFrame(buffer)
    if (tail) dispatch(tail, handlers)
  } catch (error) {
    // Abort and a dropped connection land here identically; the caller keeps
    // whatever tokens already arrived and offers a retry.
    handlers.onError?.({
      type: 'error',
      message:
        (error as Error)?.name === 'AbortError'
          ? 'Stopped.'
          : 'The connection dropped before the reply finished.',
    })
  } finally {
    // Releasing the lock lets the browser tear the socket down after an abort.
    try {
      reader.releaseLock()
    } catch {
      // Already released by the abort; nothing to do.
    }
  }
}

/**
 * POST /chats/{id}/messages — an ordinary chat turn.
 *
 * The reply's `kind` is whatever the backend's intent router decided: a plain
 * answer, or a generated document when the user simply asked for one in words.
 * The caller handles both identically, because the frames are identical.
 */
export async function streamMessage(
  chatId: string,
  content: string,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(messageStreamUrl(chatId), { content }, handlers, signal)
}

/** Routes one parsed event to its handler. */
function dispatch(event: StreamEvent, handlers: StreamHandlers): void {
  switch (event.type) {
    case 'start':
      handlers.onStart?.(event)
      break
    case 'token':
      handlers.onToken?.(event.content)
      break
    case 'done':
      handlers.onDone?.(event)
      break
    case 'error':
      handlers.onError?.(event)
      break
  }
}
