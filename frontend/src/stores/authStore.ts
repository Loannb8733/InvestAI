import type { AxiosError } from 'axios'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { queryClient } from '@/lib/queryClient'
import { apiClient } from '@/shared/api/client'

interface User {
  id: string
  email: string
  role: 'admin' | 'user'
  firstName?: string
  lastName?: string
  preferredCurrency?: string
  mfaEnabled: boolean
  telegramChatId?: string
  telegramEnabled?: boolean
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isHydrating: boolean
  error: string | null
  login: (email: string, password: string, mfaCode?: string, rememberMe?: boolean) => Promise<void>
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  hydrateSession: () => Promise<void>
  setTokens: (accessToken: string, refreshToken: string) => void
  fetchUser: () => Promise<void>
  clearError: () => void
}

function isSessionRejected(error: unknown): boolean {
  const status = (error as AxiosError | undefined)?.response?.status
  return status === 401 || status === 403
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      isHydrating: false,
      error: null,

      login: async (email: string, password: string, mfaCode?: string, rememberMe?: boolean) => {
        set({ isLoading: true, error: null })
        try {
          const response = await apiClient.post('/auth/login', {
            body: { email, password, mfa_code: mfaCode, remember_me: rememberMe ?? false },
          })
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
          await get().fetchCurrentUser()
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Login failed'
          set({ error: message, isLoading: false })
          throw error
        }
      },

      logout: async () => {
        await apiClient.post('/auth/logout').catch(() => undefined)
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
        queryClient.removeQueries()
        queryClient.cancelQueries()
      },

      refreshAccessToken: async () => {
        try {
          const { refreshToken } = get()
          const response = await apiClient.post('/auth/refresh', {
            body: refreshToken ? { refresh_token: refreshToken } : undefined,
          })
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
          })
        } catch (error) {
          if (isSessionRejected(error)) get().logout()
          throw error
        }
      },

      fetchCurrentUser: async () => {
        try {
          const user = await apiClient.get('/auth/me')
          set({
            user: {
              id: user.id,
              email: user.email,
              role: user.role as User['role'],
              firstName: user.first_name ?? undefined,
              lastName: user.last_name ?? undefined,
              preferredCurrency: user.preferred_currency || 'EUR',
              mfaEnabled: user.mfa_enabled,
              telegramChatId: user.telegram_chat_id || undefined,
              telegramEnabled: user.telegram_enabled ?? false,
            },
          })
        } catch (error) {
          if (isSessionRejected(error)) get().logout()
        }
      },

      hydrateSession: async () => {
        const { isAuthenticated, accessToken } = get()
        if (!isAuthenticated || accessToken) return
        set({ isHydrating: true })
        const refreshed = await get().refreshAccessToken().then(
          () => true,
          () => false
        )
        if (refreshed && get().isAuthenticated && get().accessToken) {
          await get().fetchCurrentUser()
        }
        set({ isHydrating: false })
      },

      setTokens: (accessToken: string, refreshToken: string) => {
        set({
          accessToken,
          refreshToken,
          isAuthenticated: true,
        })
      },

      fetchUser: async () => {
        await get().fetchCurrentUser()
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
