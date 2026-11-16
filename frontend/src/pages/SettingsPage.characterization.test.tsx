import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { ThemeProvider } from '@/components/theme-provider'
import { http } from '@/shared/api/http'
import { createFakeServer, polyfillRadixPointer } from '@/test/fakeServer'
import { authSnapshot, identityRoutes, resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { chooseOption, renderWithQuery, settle } from '@/test/render'
import SettingsPage from './SettingsPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server
const writes = () => calls.filter((c) => c.method !== 'GET')
const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/identity/${name}.json`)
}

async function openPage(mfaEnabled = false) {
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, mfaEnabled } })
  renderWithQuery(
    <ThemeProvider defaultTheme="dark" storageKey="settings-test-theme">
      <SettingsPage />
    </ThemeProvider>
  )
  await settle(() => calls.some((c) => c.url === '/auth/me'))
  await settle(() => field('monthlyDca')?.value === '250')
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(identityRoutes())
  toasts.length = 0
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SettingsPage — caractérisation', () => {
  it('pré-remplit le profil et le profil investisseur', async () => {
    await openPage()
    await golden('parametres_chargement', {
      calls,
      fields: ['email', 'firstName', 'lastName', 'monthlyDca'].map((id) => [id, field(id).value]),
      selects: screen.getAllByRole('combobox').map((el) => el.textContent),
    })
  })

  it('enregistre le profil', async () => {
    await openPage()
    type('firstName', 'Jeanne-Marie')
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer les modifications' }))
    await settle(() => toasts.length > 0)
    await golden('parametres_profil', { calls: writes(), toasts, me: calls.filter((c) => c.url === '/auth/me').length })
  })

  it('enregistre le profil investisseur', async () => {
    await openPage()
    chooseOption(screen.getAllByRole('combobox').find((el) => el.textContent === 'Modéré') as HTMLElement, 'Agressif')
    type('monthlyDca', '400')
    fireEvent.click(screen.getByRole('button', { name: /profil investisseur/i }))
    await settle(() => toasts.length > 0)
    await golden('parametres_investisseur', { calls: writes(), toasts })
  })

  it('refuse un DCA négatif sans appeler le serveur', async () => {
    await openPage()
    type('monthlyDca', '-5')
    fireEvent.click(screen.getByRole('button', { name: /profil investisseur/i }))
    await settle(() => toasts.length > 0)
    await golden('parametres_dca_invalide', { calls: writes(), toasts })
  })

  it('change le mot de passe', async () => {
    await openPage()
    type('currentPassword', 'Ancien-Passe42')
    type('newPassword', 'Nouveau-Passe42')
    type('confirmPassword', 'Nouveau-Passe42')
    fireEvent.click(screen.getByRole('button', { name: 'Changer le mot de passe' }))
    await settle(() => toasts.length > 0)
    await golden('parametres_mot_de_passe', {
      calls: writes(),
      toasts,
      cleared: ['currentPassword', 'newPassword', 'confirmPassword'].map((id) => field(id).value),
    })
  })

  it('signale un mot de passe actuel refusé', async () => {
    routes['POST /auth/change-password'] = () => ({ status: 400, data: { detail: 'Mot de passe actuel incorrect' } })
    await openPage()
    type('currentPassword', 'Faux-Passe42')
    type('newPassword', 'Nouveau-Passe42')
    type('confirmPassword', 'Nouveau-Passe42')
    fireEvent.click(screen.getByRole('button', { name: 'Changer le mot de passe' }))
    await settle(() => toasts.length > 1)
    await golden('parametres_mot_de_passe_refuse', { toasts })
  })

  it('active la MFA', async () => {
    await openPage()
    fireEvent.click(screen.getByRole('button', { name: 'Activer' }))
    const dialog = await screen.findByRole('dialog')
    const shown = within(dialog).getAllByText(/./).map((el) => el.textContent)
    fireEvent.change(within(dialog).getByPlaceholderText('000000'), { target: { value: '123456' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Vérifier et activer' }))
    await settle(() => toasts.length > 0)
    await golden('parametres_mfa_activation', { calls: writes(), toasts, shown, me: calls.filter((c) => c.url === '/auth/me').length })
  })

  it('désactive la MFA', async () => {
    await openPage(true)
    fireEvent.click(screen.getByRole('button', { name: 'Désactiver' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByPlaceholderText('000000'), { target: { value: '654321' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Désactiver la MFA' }))
    await settle(() => toasts.length > 0)
    await golden('parametres_mfa_desactivation', { calls: writes(), toasts, auth: authSnapshot().user?.mfaEnabled })
  })
})
