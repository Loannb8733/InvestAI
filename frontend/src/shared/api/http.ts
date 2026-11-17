import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/hooks/use-toast'
import { serverMessage } from './errors'

declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
  }
}

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 3000
const NO_RETRY_PATHS = ['/notifications/count', '/notifications']
const SESSIONLESS_PATHS = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/forgot-password', '/auth/reset-password']

export const http = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 60000,
})

http.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as InternalAxiosRequestConfig & { _retryCount?: number }
  if (!config) return Promise.reject(error)

  const url = config.url || ''
  if (NO_RETRY_PATHS.some((p) => url.includes(p))) {
    return Promise.reject(error)
  }

  const isNetworkError = !error.response && error.code !== 'ECONNABORTED'
  const isServerDown = error.response?.status === 502 || error.response?.status === 503

  if ((isNetworkError || isServerDown) && (config._retryCount ?? 0) < MAX_RETRIES) {
    config._retryCount = (config._retryCount ?? 0) + 1
    await new Promise((r) => setTimeout(r, RETRY_DELAY_MS))
    return http.request(config)
  }

  return Promise.reject(error)
})

http.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else if (token) {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

const notifyFailure = (error: AxiosError) => {
  if (error.config?.silent) return
  if (error.response) {
    const status = error.response.status
    const detail = (error.response.data as { detail?: string })?.detail
    if (status === 422) {
      toast({ title: 'Erreur de validation', description: detail || 'Données invalides. Vérifiez les champs.', variant: 'destructive' })
    } else if (status >= 500) {
      toast({ title: 'Erreur serveur', description: detail || 'Une erreur interne est survenue. Réessayez.', variant: 'destructive' })
    } else if (status === 403) {
      toast({ title: 'Accès refusé', description: detail || 'Vous n\'avez pas les permissions nécessaires.', variant: 'destructive' })
    } else if (status >= 400 && status !== 401 && status !== 404) {
      toast({ title: `Erreur ${status}`, description: detail || 'Une erreur est survenue.', variant: 'destructive' })
    }
  } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
    toast({ title: 'Timeout', description: 'Le serveur met trop de temps à répondre.', variant: 'destructive' })
  } else {
    toast({ title: 'Erreur réseau', description: 'Le serveur est en cours de démarrage. Rechargez la page dans quelques secondes.', variant: 'destructive' })
  }
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as typeof error.config & { _retry?: boolean }

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !SESSIONLESS_PATHS.some((path) => originalRequest.url?.startsWith(path))
    ) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`
              resolve(http(originalRequest))
            },
            reject: (err: unknown) => {
              reject(err)
            },
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        await useAuthStore.getState().refreshAccessToken()
        const { accessToken: token, user, fetchCurrentUser } = useAuthStore.getState()

        if (token) {
          processQueue(null, token)
          if (!user) void fetchCurrentUser()
          originalRequest.headers.Authorization = `Bearer ${token}`
          return http(originalRequest)
        } else {
          processQueue(new Error('No token after refresh'), null)
          useAuthStore.getState().logout()
        }
      } catch (refreshError) {
        processQueue(refreshError, null)
        const reason = serverMessage(refreshError)
        if (reason?.includes('mot de passe')) {
          toast({ title: 'Session expirée', description: reason, variant: 'destructive' })
        }
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    notifyFailure(error)
    return Promise.reject(error)
  }
)
