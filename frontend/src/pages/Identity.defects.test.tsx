import type { ReactElement } from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ThemeProvider } from '@/components/theme-provider'
import { http } from '@/shared/api/http'
import { createFakeServer, polyfillRadixPointer } from '@/test/fakeServer'
import { identityRoutes, resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { renderWithQuery, settle } from '@/test/render'
import AdminPage from './AdminPage'
import LoginPage from './LoginPage'
import RegisterPage from './RegisterPage'
import ResetPasswordPage from './ResetPasswordPage'
import SettingsPage from './SettingsPage'

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
const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })
const submit = () => fireEvent.click(document.querySelector('button[type="submit"]') as HTMLButtonElement)
const count = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url).length
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const refuse = (detail: string, status = 400) => () => ({ status, data: { detail } })

function renderAt(path: string, element: ReactElement) {
  return renderWithQuery(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={path.split('?')[0]} element={element} />
        <Route path="*" element={<p>ailleurs</p>} />
      </Routes>
    </MemoryRouter>
  )
}

async function openSettings() {
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
  renderWithQuery(
    <ThemeProvider defaultTheme="dark" storageKey="identity-defects-theme">
      <SettingsPage />
    </ThemeProvider>
  )
  await settle(() => field('monthlyDca')?.value === '250')
}

function login() {
  renderAt('/login', <LoginPage />)
  type('email', 'jeanne@example.com')
  type('password', 'Secret-42xyz')
  submit()
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

describe('identity — défauts corrigés', () => {
  it('un mot de passe refusé ne déclenche ni refresh ni déconnexion', async () => {
    routes['POST /auth/login'] = refuse('Email ou mot de passe invalide', 401)
    login()
    await screen.findByText('Email ou mot de passe invalide')
    expect(calls.map((c) => c.url)).toEqual(['/auth/login'])
  })

  it('l’erreur de connexion affiche le message du serveur, une seule fois', async () => {
    routes['POST /auth/login'] = refuse('Email ou mot de passe invalide', 401)
    login()
    await screen.findByText('Email ou mot de passe invalide')
    await pause(50)
    expect(screen.queryByText(/Request failed/)).not.toBeInTheDocument()
    expect(toasts).toEqual([])
  })

  it('un compte protégé par MFA demande le code puis se connecte', async () => {
    routes['POST /auth/login'] = (config) =>
      JSON.parse(String(config.data)).mfa_code
        ? { status: 200, data: { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' } }
        : { status: 400, data: { detail: 'MFA code required' } }
    login()
    await settle(() => field('mfaCode') !== null)
    expect(screen.queryByText('MFA code required')).not.toBeInTheDocument()
    type('mfaCode', '123456')
    submit()
    await screen.findByText('ailleurs')
    expect(calls.filter((c) => c.url === '/auth/login').map((c) => (c.body as { mfa_code?: string }).mfa_code)).toEqual([
      undefined,
      '123456',
    ])
    expect(toasts.filter((t) => t.variant === 'destructive')).toEqual([])
  })

  it('une inscription refusée affiche le message du serveur dans une seule notification', async () => {
    routes['POST /auth/register'] = refuse('Cette adresse est déjà utilisée')
    renderAt('/register', <RegisterPage />)
    type('email', 'jeanne@example.com')
    type('password', 'Solide-Passe42')
    type('confirmPassword', 'Solide-Passe42')
    fireEvent.click(field('acceptTerms'))
    submit()
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts).toEqual([
      { variant: 'destructive', title: "Erreur d'inscription", description: 'Cette adresse est déjà utilisée' },
    ])
    expect(screen.getByText('Cette adresse est déjà utilisée')).toBeInTheDocument()
  })

  it('un mot de passe actuel refusé n’affiche qu’une notification', async () => {
    routes['POST /auth/change-password'] = refuse('Mot de passe actuel incorrect')
    await openSettings()
    type('currentPassword', 'Faux-Passe42')
    type('newPassword', 'Nouveau-Passe42')
    type('confirmPassword', 'Nouveau-Passe42')
    fireEvent.click(screen.getByRole('button', { name: 'Changer le mot de passe' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts).toEqual([{ title: 'Erreur', description: 'Mot de passe actuel incorrect', variant: 'destructive' }])
  })

  it('un code MFA refusé n’affiche qu’une notification', async () => {
    routes['POST /auth/mfa/verify'] = refuse('Code MFA invalide')
    await openSettings()
    fireEvent.click(screen.getByRole('button', { name: 'Activer' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByPlaceholderText('000000'), { target: { value: '000000' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Vérifier et activer' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts.map((t) => t.title)).toEqual(['Code invalide'])
  })

  it('une réinitialisation refusée n’affiche qu’une notification', async () => {
    routes['POST /auth/reset-password'] = refuse('Lien expiré')
    renderAt('/reset-password?token=tok-123', <ResetPasswordPage />)
    type('password', 'Nouveau-Passe42')
    type('confirmPassword', 'Nouveau-Passe42')
    submit()
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts).toEqual([{ variant: 'destructive', title: 'Erreur', description: 'Lien expiré' }])
  })

  it('l’activation MFA affiche les codes de secours', async () => {
    await openSettings()
    fireEvent.click(screen.getByRole('button', { name: 'Activer' }))
    const dialog = await screen.findByRole('dialog')
    const list = within(dialog).getByRole('list', { name: 'Codes de secours' })
    expect(within(list).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['AAAA-1111', 'BBBB-2222'])
  })

  it('enregistrer le profil ou le profil investisseur ne relit pas /auth/me', async () => {
    await openSettings()
    const before = count('GET', '/auth/me')
    type('firstName', 'Jeanne-Marie')
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer les modifications' }))
    await settle(() => toasts.length === 1)
    type('monthlyDca', '400')
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer le profil investisseur' }))
    await settle(() => toasts.length === 2)
    await pause(50)
    expect(count('GET', '/auth/me')).toBe(before)
    expect(field('firstName').value).toBe('Jeanne-Marie')
  })

  it('une liste d’utilisateurs indisponible n’affiche que l’état d’erreur', async () => {
    routes['GET /users'] = refuse('boom', 500)
    renderWithQuery(<AdminPage />)
    await screen.findByText("Impossible de charger l'administration")
    await pause(50)
    expect(toasts).toEqual([])
  })

  it('les rôles s’affichent en français', async () => {
    renderWithQuery(<AdminPage />)
    await screen.findByText('paul@example.com')
    const row = (email: string) => screen.getByText(email).closest('tr') as HTMLElement
    expect(within(row('jeanne@example.com')).getByText('Administrateur')).toBeInTheDocument()
    expect(within(row('paul@example.com')).getByText('Utilisateur')).toBeInTheDocument()
    expect(screen.queryByText('admin')).not.toBeInTheDocument()
  })

  it('le rôle du profil s’affiche en français', async () => {
    await openSettings()
    expect(field('role').value).toBe('Utilisateur')
  })
})
