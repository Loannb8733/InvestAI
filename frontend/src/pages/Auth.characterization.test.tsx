import { act, type ReactElement } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { http } from '@/shared/api/http'
import { useAuthStore } from '@/stores/authStore'
import { createFakeServer, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { authSnapshot, identityRoutes, resetAuth } from '@/test/identityFixtures'
import { renderWithQuery, settle } from '@/test/render'
import ForgotPasswordPage from './ForgotPasswordPage'
import LoginPage from './LoginPage'
import RegisterPage from './RegisterPage'
import ResetPasswordPage from './ResetPasswordPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})
vi.mock('@/components/ui/aurora-canvas', () => ({ default: () => null }))

const server = createFakeServer()
const { calls, routes } = server

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderAt(path: string, element: ReactElement) {
  const route = path.split('?')[0]
  return renderWithQuery(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={element} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  )
}

const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })
const submit = () => fireEvent.click(document.querySelector('button[type="submit"]') as HTMLButtonElement)
const where = () => screen.queryByTestId('where')?.textContent ?? null

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/identity/${name}.json`)
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(identityRoutes())
  toasts.length = 0
  resetAuth()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Connexion', () => {
  async function login(remember = false) {
    renderAt('/login', <LoginPage />)
    type('email', 'jeanne@example.com')
    type('password', 'Secret-42xyz')
    if (remember) fireEvent.click(field('rememberMe'))
    submit()
  }

  it('connecte, charge le profil et ouvre l’accueil', async () => {
    await login()
    await settle(() => where() === '/')
    await golden('connexion_reussie', { calls, toasts, where: where(), auth: authSnapshot() })
  })

  it('transmet « rester connecté »', async () => {
    await login(true)
    await settle(() => where() === '/')
    await golden('connexion_memorisee', { login: calls.find((c) => c.url === '/auth/login') })
  })

  it('réagit à un mot de passe refusé', async () => {
    routes['POST /auth/login'] = () => ({ status: 401, data: { detail: 'Email ou mot de passe invalide' } })
    routes['POST /auth/refresh'] = () => ({ status: 401, data: { detail: 'Refresh token invalide' } })
    await login()
    await screen.findByText('Email ou mot de passe invalide')
    await golden('connexion_refusee', { calls, toasts, where: where(), auth: authSnapshot() })
  })

  it('réagit à un compte protégé par MFA', async () => {
    routes['POST /auth/login'] = () => ({ status: 400, data: { detail: 'MFA code required' } })
    await login()
    await settle(() => document.getElementById('mfaCode') !== null)
    await golden('connexion_mfa_requise', {
      calls,
      toasts,
      mfaField: document.getElementById('mfaCode') !== null,
      auth: authSnapshot(),
    })
  })
})

describe('Session', () => {
  it('restaure une session après un rechargement de page', async () => {
    resetAuth({ isAuthenticated: true })
    await act(() => useAuthStore.getState().hydrateSession())
    await golden('session_restauree', { calls, auth: authSnapshot() })
  })

  it('ferme une session que le serveur refuse', async () => {
    resetAuth({ isAuthenticated: true })
    routes['POST /auth/refresh'] = () => ({ status: 401, data: { detail: 'Refresh token invalide' } })
    await act(() => useAuthStore.getState().hydrateSession())
    await golden('session_refusee', { calls, auth: authSnapshot() })
  })

  it('déconnecte', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1' })
    await act(() => useAuthStore.getState().logout())
    await golden('deconnexion', { calls, auth: authSnapshot() })
  })
})

describe('Inscription', () => {
  function fill() {
    renderAt('/register', <RegisterPage />)
    type('firstName', 'Jeanne')
    type('lastName', 'Martin')
    type('email', 'jeanne@example.com')
    type('password', 'Solide-Passe42')
    type('confirmPassword', 'Solide-Passe42')
    fireEvent.click(field('acceptTerms'))
    submit()
  }

  it('inscrit puis renvoie vers la connexion', async () => {
    fill()
    await settle(() => where() === '/login')
    await golden('inscription_reussie', { calls, toasts, where: where() })
  })

  it('signale une inscription refusée', async () => {
    routes['POST /auth/register'] = () => ({ status: 400, data: { detail: 'Cette adresse est déjà utilisée' } })
    fill()
    await settle(() => toasts.some((t) => t.title === 'Erreur d\'inscription'))
    await golden('inscription_refusee', { calls, toasts, where: where(), text: visibleText() })
  })
})

describe('Récupération du compte', () => {
  it('demande un lien de réinitialisation', async () => {
    renderAt('/forgot-password', <ForgotPasswordPage />)
    type('email', 'jeanne@example.com')
    submit()
    await settle(() => calls.length > 0)
    await screen.findByRole('button', { name: /autre adresse|renvoyer|réessayer/i })
    await golden('mot_de_passe_oublie', { calls, toasts, text: visibleText() })
  })

  it('réinitialise le mot de passe avec le jeton du lien', async () => {
    renderAt('/reset-password?token=tok-123', <ResetPasswordPage />)
    type('password', 'Nouveau-Passe42')
    type('confirmPassword', 'Nouveau-Passe42')
    submit()
    await settle(() => calls.length > 0)
    await screen.findByRole('button', { name: /connexion|se connecter/i })
    await golden('reinitialisation', { calls, toasts, text: visibleText() })
  })

  it('refuse un lien sans jeton', async () => {
    renderAt('/reset-password', <ResetPasswordPage />)
    await screen.findByText('Lien de réinitialisation invalide.')
    await golden('reinitialisation_sans_jeton', { calls, text: visibleText() })
  })
})
