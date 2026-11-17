import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/shared/api/client', () => ({ apiClient: client }))

type Outcome = { ok: unknown } | { fail: unknown }

function serve(routes: Record<string, Outcome>) {
  const answer = (route: string) => {
    const outcome = routes[route] ?? { ok: {} }
    return 'ok' in outcome ? Promise.resolve(outcome.ok) : Promise.reject(outcome.fail)
  }
  client.get.mockImplementation(answer)
  client.post.mockImplementation(answer)
}

const posted = (route: string) => client.post.mock.calls.some(([called]) => called === route)

const rejected = { response: { status: 401, data: {} } }
const transientFailures: Array<[string, unknown]> = [
  ['429', { response: { status: 429, data: {} } }],
  ['503', { response: { status: 503, data: {} } }],
  ['panne réseau', new Error('Network Error')],
]

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
    vi.clearAllMocks()
    serve({})
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
      serve({
        '/auth/login': { ok: { access_token: 'access123', refresh_token: 'refresh123' } },
        '/auth/me': {
          ok: { id: '1', email: 'test@test.com', role: 'user', first_name: 'Test', last_name: 'User', mfa_enabled: false },
        },
      })

      await useAuthStore.getState().login('test@test.com', 'password')

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('access123')
      expect(state.refreshToken).toBe('refresh123')
      expect(state.isAuthenticated).toBe(true)
      expect(state.isLoading).toBe(false)
      expect(state.user?.email).toBe('test@test.com')
    })

    it('keeps the server message on failure', async () => {
      serve({ '/auth/login': { fail: { response: { status: 401, data: { detail: 'Email ou mot de passe invalide' } } } } })

      await expect(useAuthStore.getState().login('bad@test.com', 'wrong')).rejects.toBeTruthy()

      const state = useAuthStore.getState()
      expect(state.error).toBe('Email ou mot de passe invalide')
      expect(state.isLoading).toBe(false)
      expect(state.isAuthenticated).toBe(false)
    })
  })

  it('explains a failure without server message in French', async () => {
    serve({ '/auth/login': { fail: new Error('Network Error') } })

    await expect(useAuthStore.getState().login('a@test.com', 'x')).rejects.toThrow()

    expect(useAuthStore.getState().error).toBe('Connexion impossible pour le moment. Réessayez.')
  })

  describe('logout', () => {
    it('clears all auth state', async () => {
      useAuthStore.setState({
        user: { id: '1', email: 'a@b.com', role: 'user', mfaEnabled: false },
        accessToken: 'token',
        refreshToken: 'refresh',
        isAuthenticated: true,
        error: 'some error',
      })

      await useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBeNull()
    })

    it('clears the session even when the server call fails', async () => {
      serve({ '/auth/logout': { fail: new Error('Network Error') } })
      useAuthStore.setState({ accessToken: 'token', isAuthenticated: true })

      await useAuthStore.getState().logout()

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
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
      serve({ '/auth/refresh': { ok: { access_token: 'new-access', refresh_token: 'new-refresh' } } })

      await useAuthStore.getState().refreshAccessToken()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('new-access')
      expect(state.refreshToken).toBe('new-refresh')
      expect(client.post).toHaveBeenCalledWith('/auth/refresh', { body: { refresh_token: 'old-refresh' } })
    })

    it('logs out and reports the failure when the server rejects the session', async () => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/refresh': { fail: rejected } })

      await expect(useAuthStore.getState().refreshAccessToken()).rejects.toBe(rejected)

      await vi.waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false))
    })

    it.each(transientFailures)('keeps the session and reports the failure on %s', async (_, failure) => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/refresh': { fail: failure } })

      await expect(useAuthStore.getState().refreshAccessToken()).rejects.toBe(failure)

      expect(posted('/auth/logout')).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })
  })

  describe('fetchCurrentUser', () => {
    it('sets user on success', async () => {
      serve({
        '/auth/me': {
          ok: { id: '42', email: 'admin@test.com', role: 'admin', first_name: 'Admin', last_name: 'User', mfa_enabled: true },
        },
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

    it('logs out when the server rejects the session', async () => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/me': { fail: rejected } })

      await useAuthStore.getState().fetchCurrentUser()

      await vi.waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false))
    })

    it.each(transientFailures)('keeps the session on %s', async (_, failure) => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/me': { fail: failure } })

      await useAuthStore.getState().fetchCurrentUser()

      expect(posted('/auth/logout')).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })
  })

  describe('hydrateSession', () => {
    it('closes a session the server rejects when the page loads', async () => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/refresh': { fail: rejected } })

      await useAuthStore.getState().hydrateSession()

      await vi.waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false))
      expect(useAuthStore.getState().isHydrating).toBe(false)
    })

    it.each(transientFailures)('keeps the session and stops waiting on %s', async (_, failure) => {
      useAuthStore.setState({ isAuthenticated: true })
      serve({ '/auth/refresh': { fail: failure } })

      await useAuthStore.getState().hydrateSession()

      expect(posted('/auth/logout')).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(useAuthStore.getState().isHydrating).toBe(false)
    })
  })
})
