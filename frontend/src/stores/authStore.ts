import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi } from '@/services/api'

interface User {
  id: string
  email: string
  role: 'admin' | 'user'
  firstName?: string
  lastName?: string
  preferredCurrency?: string
  mfaEnabled: boolean
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string, mfaCode?: string) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  setTokens: (accessToken: string, refreshToken: string) => void
  fetchUser: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string, mfaCode?: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.login(email, password, mfaCode)
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

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },

      refreshAccessToken: async () => {
        const { refreshToken } = get()
        if (!refreshToken) {
          get().logout()
          return
        }

        try {
          const response = await authApi.refresh(refreshToken)
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
          })
        } catch {
          get().logout()
        }
      },

      fetchCurrentUser: async () => {
        try {
          const user = await authApi.getCurrentUser()
          set({
            user: {
              id: user.id,
              email: user.email,
              role: user.role,
              firstName: user.first_name,
              lastName: user.last_name,
              preferredCurrency: user.preferred_currency || 'EUR',
              mfaEnabled: user.mfa_enabled,
            },
          })
        } catch {
          get().logout()
        }
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
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        user: state.user,
      }),
    }
  )
)
