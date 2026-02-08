import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

// Mock the API module
vi.mock('@/services/api', () => ({
  authApi: {
    login: vi.fn(),
    refresh: vi.fn(),
    getCurrentUser: vi.fn(),
  },
}))

import { authApi } from '@/services/api'

const mockedAuthApi = vi.mocked(authApi)

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has null user', () => {
      expect(useAuthStore.getState().user).toBeNull()
    })

    it('is not authenticated', () => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('has no tokens', () => {
      expect(useAuthStore.getState().accessToken).toBeNull()
      expect(useAuthStore.getState().refreshToken).toBeNull()
    })

    it('is not loading', () => {
      expect(useAuthStore.getState().isLoading).toBe(false)
    })

    it('has no error', () => {
      expect(useAuthStore.getState().error).toBeNull()
    })
  })

  describe('login', () => {
    it('sets tokens and isAuthenticated on success', async () => {
      mockedAuthApi.login.mockResolvedValue({
        access_token: 'access123',
        refresh_token: 'refresh123',
      })
      mockedAuthApi.getCurrentUser.mockResolvedValue({
        id: '1',
        email: 'test@test.com',
        role: 'user',
        first_name: 'Test',
        last_name: 'User',
        mfa_enabled: false,
      })

      await useAuthStore.getState().login('test@test.com', 'password')

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('access123')
      expect(state.refreshToken).toBe('refresh123')
      expect(state.isAuthenticated).toBe(true)
      expect(state.isLoading).toBe(false)
      expect(state.user?.email).toBe('test@test.com')
    })

    it('sets error on failure', async () => {
      mockedAuthApi.login.mockRejectedValue(new Error('Invalid credentials'))

      await expect(
        useAuthStore.getState().login('bad@test.com', 'wrong')
      ).rejects.toThrow()

      const state = useAuthStore.getState()
      expect(state.error).toBe('Invalid credentials')
      expect(state.isLoading).toBe(false)
      expect(state.isAuthenticated).toBe(false)
    })
  })

  describe('logout', () => {
    it('clears all auth state', () => {
      useAuthStore.setState({
        user: { id: '1', email: 'a@b.com', role: 'user', mfaEnabled: false },
        accessToken: 'token',
        refreshToken: 'refresh',
        isAuthenticated: true,
        error: 'some error',
      })

      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBeNull()
    })
  })

  describe('setTokens', () => {
    it('sets tokens and marks as authenticated', () => {
      useAuthStore.getState().setTokens('new-access', 'new-refresh')

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('new-access')
      expect(state.refreshToken).toBe('new-refresh')
      expect(state.isAuthenticated).toBe(true)
    })
  })

  describe('clearError', () => {
    it('clears error state', () => {
      useAuthStore.setState({ error: 'some error' })
      useAuthStore.getState().clearError()
      expect(useAuthStore.getState().error).toBeNull()
    })
  })

  describe('refreshAccessToken', () => {
    it('refreshes tokens on success', async () => {
      useAuthStore.setState({ refreshToken: 'old-refresh' })
      mockedAuthApi.refresh.mockResolvedValue({
        access_token: 'new-access',
        refresh_token: 'new-refresh',
      })

      await useAuthStore.getState().refreshAccessToken()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('new-access')
      expect(state.refreshToken).toBe('new-refresh')
    })

    it('logs out when no refresh token', async () => {
      useAuthStore.setState({
        refreshToken: null,
        isAuthenticated: true,
        accessToken: 'some-token',
      })

      await useAuthStore.getState().refreshAccessToken()

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('logs out on refresh failure', async () => {
      useAuthStore.setState({
        refreshToken: 'old-refresh',
        isAuthenticated: true,
      })
      mockedAuthApi.refresh.mockRejectedValue(new Error('expired'))

      await useAuthStore.getState().refreshAccessToken()

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('fetchCurrentUser', () => {
    it('sets user on success', async () => {
      mockedAuthApi.getCurrentUser.mockResolvedValue({
        id: '42',
        email: 'admin@test.com',
        role: 'admin',
        first_name: 'Admin',
        last_name: 'User',
        mfa_enabled: true,
      })

      await useAuthStore.getState().fetchCurrentUser()

      const user = useAuthStore.getState().user
      expect(user?.id).toBe('42')
      expect(user?.email).toBe('admin@test.com')
      expect(user?.role).toBe('admin')
      expect(user?.firstName).toBe('Admin')
      expect(user?.lastName).toBe('User')
      expect(user?.mfaEnabled).toBe(true)
    })

    it('logs out on failure', async () => {
      useAuthStore.setState({ isAuthenticated: true })
      mockedAuthApi.getCurrentUser.mockRejectedValue(new Error('unauthorized'))

      await useAuthStore.getState().fetchCurrentUser()

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })
})
