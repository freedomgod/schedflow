import axios from 'axios'
import type { AxiosInstance, AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import { expireSession } from '@/utils/session'

/**
 * Endpoints that verify credentials. Their 401 means "wrong password", not an
 * expired session, so they must not trigger the logout flow.
 */
const AUTH_ENDPOINTS = ['/auth/login', '/auth/init-status', '/auth/init-setup']

function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false
  return AUTH_ENDPOINTS.some((path) => url.endsWith(path))
}

function createClient(baseURL: string): AxiosInstance {
  const instance: AxiosInstance = axios.create({
    baseURL,
    timeout: 10000,
    headers: { 'Content-Type': 'application/json' },
  })

  instance.interceptors.request.use((config) => {
    const token = localStorage.getItem('schedflow_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  instance.interceptors.response.use(
    (response) => {
      const { code, message, data } = response.data
      if (code !== 0) {
        ElMessage.error(message || 'Request failed')
        return Promise.reject(new Error(message))
      }
      return data
    },
    (error: AxiosError<{ detail?: unknown; message?: string }>) => {
      const status = error.response?.status
      if ((status === 401 || status === 403) && !isAuthEndpoint(error.config?.url)) {
        // The session handler clears auth state, redirects to /login and shows
        // one readable notice. Reject quietly so the backend's raw
        // "Forbidden: invalid or missing credentials" never reaches the user.
        expireSession()
        return Promise.reject(error)
      }

      const data = error.response?.data
      let msg: string
      if (data?.detail) {
        if (Array.isArray(data.detail) && data.detail.length > 0) {
          msg = data.detail.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
        } else {
          msg = String(data.detail)
        }
      } else if (data?.message) {
        msg = data.message
      } else {
        msg = error.message || 'Network error'
      }
      ElMessage.error(msg)
      return Promise.reject(error)
    },
  )

  return instance
}

/** Management API client (auth / settings / components). */
const client: AxiosInstance = createClient(import.meta.env.VITE_API_BASE_URL || '/api/v1')

/** scheduling API client (jobs / scheduler / logs). */
const schedulerClient: AxiosInstance = createClient(import.meta.env.VITE_SCHEDULER_API_BASE_URL || '/api')

export { schedulerClient }
export default client
