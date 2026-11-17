import type { AxiosError } from 'axios'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { queryClient } from '@/lib/queryClient'
import { apiClient, type Schema } from '@/shared/api/client'
import { serverMessage } from '@/shared/api/errors'

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
  applyProfile: (profile: Schema<'ProfileResponse'>) => void
  hydrateSession: () => Promise<void>
  setTokens: (accessToken: string, refreshToken: string) => void
  fetchUser: () => Promise<void>
  clearError: () => void
}

const toUser = (profile: Schema<'ProfileResponse'>): User => ({
  id: profile.id,
  email: profile.email,
  role: profile.role as User['role'],
  firstName: profile.first_name ?? undefined,
  lastName: profile.last_name ?? undefined,
  preferredCurrency: profile.preferred_currency || 'EUR',
  mfaEnabled: profile.mfa_enabled,
  telegramChatId: profile.telegram_chat_id || undefined,
  telegramEnabled: profile.telegram_enabled ?? false,
})

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
            silent: true,
          })
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
          await get().fetchCurrentUser()
        } catch (error: unknown) {
          const message = serverMessage(error) ?? 'Connexion impossible pour le moment. Réessayez.'
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
          set({ user: toUser(await apiClient.get('/auth/me')) })
        } catch (error) {
          if (isSessionRejected(error)) get().logout()
        }
      },

      applyProfile: (profile) => set({ user: toUser(profile) }),

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
