import axios, { AxiosError, type AxiosInstance } from 'axios'
import { supabase } from '../lib/supabase'
import type { HealthResponse } from '../types'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** Single Axios instance used by every service module. */
export const api: AxiosInstance = axios.create({
  baseURL,
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

/** HTTP status of a failed request, or undefined for network / unknown errors. */
export function apiErrorStatus(error: unknown): number | undefined {
  return error instanceof AxiosError ? error.response?.status : undefined
}

/** Best available human-readable message for a failed request. */
export function apiErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)
      ?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: unknown }
      if (typeof first?.msg === 'string') return first.msg
    }
    if (error.code === 'ERR_NETWORK') {
      return 'Cannot reach the Applify server. Check your connection and try again.'
    }
    if (error.message) return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/** GET /health — used by the Phase 1 integration check. */
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health')
  return data
}

export default api
