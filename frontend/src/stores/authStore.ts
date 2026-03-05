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
  logout: () => void
  refreshAccessToken: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  hydrateSession: () => Promise<void>
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
      isHydrating: false,
      error: null,

      login: async (email: string, password: string, mfaCode?: string, rememberMe?: boolean) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.login(email, password, mfaCode, rememberMe)
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
        // Clear server-side cookies
        authApi.logout()
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },

      refreshAccessToken: async () => {
        try {
          // Try cookie-based refresh first (no token needed), fall back to stored token
          const { refreshToken } = get()
          const response = await authApi.refresh(refreshToken || undefined)
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
              telegramChatId: user.telegram_chat_id || undefined,
              telegramEnabled: user.telegram_enabled ?? false,
            },
          })
        } catch {
          get().logout()
        }
      },

      hydrateSession: async () => {
        const { isAuthenticated, accessToken } = get()
        // Only hydrate if store says authenticated but token is missing (page refresh)
        if (!isAuthenticated) return
        if (accessToken) return // Already have a token, no need to hydrate

        set({ isHydrating: true })
        try {
          // Try to refresh using the httpOnly cookie.
          // refreshAccessToken() calls logout() internally on failure,
          // so we just check the result.
          await get().refreshAccessToken()
          // If refresh succeeded (still authenticated), fetch fresh user data
          if (get().isAuthenticated && get().accessToken) {
            await get().fetchCurrentUser()
          }
        } finally {
          set({ isHydrating: false })
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
      // Do NOT persist tokens to localStorage — they are already in httpOnly cookies.
      // Storing JWTs in JS-accessible storage exposes them to XSS attacks.
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        user: state.user,
      }),
    }
  )
)
