import axios, { type AxiosInstance } from 'axios'
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
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** GET /health — used by the Phase 1 integration check. */
export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health')
  return data
}

export default api
