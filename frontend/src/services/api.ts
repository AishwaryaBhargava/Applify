import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import { supabase } from '../lib/supabase'
import { pushToast } from '../store/toastStore'
import type { HealthResponse } from '../types'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/**
 * Long enough for a detailed analysis on a cold backend, short enough that a
 * dead server is reported rather than spun on forever. The resume upload
 * overrides it — see `UPLOAD_TIMEOUT_MS` in services/profile.
 */
export const REQUEST_TIMEOUT_MS = 30_000

/** Single Axios instance used by every service module. */
export const api: AxiosInstance = axios.create({
  baseURL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * Injects the current Supabase session access token as a Bearer token on
 * every outgoing request. Requests made before a session exists are sent
 * unauthenticated and the backend replies 401.
 */
api.interceptors.request.use(async (config) => {
  try {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  } catch {
    // Supabase unreachable (or unconfigured): send the request unauthenticated
    // and let the backend reply 401 rather than failing before it is sent.
  }
  return config
})

/* ------------------------------------------------------------------ */
/* Error classification                                                */
/* ------------------------------------------------------------------ */

/** HTTP status of a failed request, or undefined for network / unknown errors. */
export function apiErrorStatus(error: unknown): number | undefined {
  return error instanceof AxiosError ? error.response?.status : undefined
}

/**
 * The parsed response body of a failed request, for the one caller that needs
 * more than `detail`: `PATCH /profile` adds an `errors` list the profile page
 * highlights individual inputs from.
 */
export function apiErrorBody<T = unknown>(error: unknown): T | undefined {
  return error instanceof AxiosError
    ? (error.response?.data as T | undefined)
    : undefined
}

/** The backend's `detail`, in whichever of its two shapes it arrived. */
function responseDetail(error: unknown): string {
  if (!(error instanceof AxiosError)) return ''
  const detail = (error.response?.data as { detail?: unknown } | undefined)
    ?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: unknown }
    if (typeof first?.msg === 'string') return first.msg
  }
  return ''
}

/** No reply at all: the request timed out, or never reached the server. */
export function isTransportError(error: unknown): boolean {
  if (!(error instanceof AxiosError)) return false
  if (error.response) return false
  return (
    error.code === 'ECONNABORTED' ||
    error.code === 'ETIMEDOUT' ||
    error.code === 'ERR_NETWORK'
  )
}

/** Anything the model providers or the gateway report as "slow down". */
const RATE_LIMIT_PATTERN =
  /rate.?limit|too many requests|quota|capacity|overloaded|try again later/i

/**
 * True when the failure is a rate limit rather than a fault.
 *
 * A 429 always is. Azure and Groq limits also surface through the backend as a
 * 502 or 503 with the provider's own wording, so those are matched on the
 * message rather than the status alone.
 */
export function isRateLimitError(error: unknown): boolean {
  const status = apiErrorStatus(error)
  if (status === 429) return true
  if (status === 502 || status === 503) {
    return RATE_LIMIT_PATTERN.test(responseDetail(error))
  }
  return false
}

/** Copy shown while the automatic retry of a rate-limited call is in flight. */
export const RETRYING_MESSAGE = 'Taking a moment, retrying...'

/** Copy shown once a rate-limited call has failed its retry too. */
export const RATE_LIMITED_MESSAGE =
  'The AI provider is rate limited right now. Give it a minute and try again.'

/** Best available human-readable message for a failed request. */
export function apiErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (isRateLimitError(error)) return RATE_LIMITED_MESSAGE

  if (error instanceof AxiosError) {
    const detail = responseDetail(error)
    if (detail.trim()) return detail
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      return 'That took too long to answer. Check your connection and try again.'
    }
    if (error.code === 'ERR_NETWORK') {
      return 'Cannot reach the Applify server. Check your connection and try again.'
    }
    if (error.response && error.response.status >= 500) {
      return 'The Applify server hit an error. Please try again in a moment.'
    }
    if (error.message) return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/* ------------------------------------------------------------------ */
/* Retry                                                               */
/* ------------------------------------------------------------------ */

/** Our own bookkeeping on a request config, so a retry never loops. */
interface RetryableConfig extends InternalAxiosRequestConfig {
  /** Set once the automatic retry has been spent. */
  applifyRetried?: boolean
  /** Opts a specific call out of the automatic retry entirely. */
  applifyNoRetry?: boolean
}

/** How long to wait before the single automatic retry. */
const RETRY_DELAY_MS = 700
/** A rate limit needs longer than a dropped packet to clear. */
const RATE_LIMIT_RETRY_DELAY_MS = 1_800

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Whether repeating this request is safe.
 *
 * GET and DELETE are idempotent by HTTP, PATCH is idempotent as the backend
 * implements it (a whole-section replace, a status set), and
 * `POST /chats/{id}/analyze` is idempotent by contract — without `force` it
 * returns the analysis it already stored. `POST /chats` and
 * `POST /profile/upload` are not: a retry could open a second chat or bill a
 * second parse, so those surface the error and let the user press the button
 * again themselves.
 */
function isRepeatable(config: RetryableConfig): boolean {
  const method = (config.method ?? 'get').toLowerCase()
  if (method === 'get' || method === 'head' || method === 'delete') return true
  if (method === 'patch' || method === 'put') return true
  if (method === 'post') return /\/analyze$/.test(config.url ?? '')
  return false
}

/**
 * One automatic retry, then the error.
 *
 * A timeout or a dropped connection is retried once because the usual cause is
 * a single lost request rather than a broken server. A rate limit is retried
 * once too, behind the "Taking a moment, retrying..." toast, because the
 * providers' limits are short windows. Everything else — a 4xx the user has to
 * act on, a genuine 500 — is returned immediately: retrying it would only make
 * the user wait longer to read the same message.
 */
api.interceptors.response.use(undefined, async (error: unknown) => {
  const config = (error as AxiosError).config as RetryableConfig | undefined

  if (apiErrorStatus(error) === 401) {
    // Imported lazily: the session module reaches back into every store, and
    // several of those import this file for `apiErrorMessage`.
    const { handleSessionExpired } = await import('../store/sessionExpired')
    void handleSessionExpired()
    return Promise.reject(error)
  }

  const rateLimited = isRateLimitError(error)
  const retryable = rateLimited || isTransportError(error)

  if (
    !config ||
    config.applifyRetried ||
    config.applifyNoRetry ||
    !retryable ||
    !isRepeatable(config)
  ) {
    return Promise.reject(error)
  }

  config.applifyRetried = true
  if (rateLimited) pushToast(RETRYING_MESSAGE, 'info')
  await delay(rateLimited ? RATE_LIMIT_RETRY_DELAY_MS : RETRY_DELAY_MS)
  return api.request(config)
})

/**
 * GET /health — the backend status pill.
 *
 * Opted out of the automatic retry and given a short timeout: this is a poll
 * whose whole job is to say quickly whether the server is up, and a retry
 * would only delay the honest answer.
 */
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health', {
    timeout: 8_000,
    applifyNoRetry: true,
  } as never)
  return data
}

export default api
