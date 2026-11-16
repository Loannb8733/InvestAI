import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { identityRoutes } from '@/test/identityFixtures'
import { chooseOption, renderWithQuery, settle } from '@/test/render'
import AdminPage from './AdminPage'

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

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/identity/${name}.json`)
}

async function openPage() {
  renderWithQuery(<AdminPage />)
  await screen.findByText('paul@example.com')
}

beforeAll(() => {
  process.env.TZ = 'UTC'
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

describe('AdminPage — caractérisation', () => {
  it('liste les utilisateurs', async () => {
    await openPage()
    await golden('admin_liste', { calls, text: visibleText() })
  })

  it('signale une liste indisponible', async () => {
    routes['GET /users'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<AdminPage />)
    await screen.findByText("Impossible de charger l'administration")
    await golden('admin_liste_erreur', { toasts })
  })

  it('crée un utilisateur', async () => {
    await openPage()
    fireEvent.click(screen.getByRole('button', { name: /Nouvel utilisateur|Ajouter/ }))
    const dialog = await screen.findByRole('dialog')
    const set = (id: string, value: string) =>
      fireEvent.change(within(dialog).getByLabelText(id), { target: { value } })
    set('Email', 'lea@example.com')
    set('Mot de passe', 'Solide-Passe42')
    set('Prénom', 'Léa')
    set('Nom', 'Durand')
    chooseOption(within(dialog).getByRole('combobox'), 'Administrateur')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await golden('admin_creation', { calls: writes(), toasts })
  })

  it('exige email et mot de passe', async () => {
    await openPage()
    fireEvent.click(screen.getByRole('button', { name: /Nouvel utilisateur|Ajouter/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await golden('admin_creation_incomplete', { calls: writes(), toasts })
  })

  it('active un compte inactif', async () => {
    await openPage()
    fireEvent.click(screen.getByRole('button', { name: 'Activer' }))
    await settle(() => toasts.length > 0)
    await golden('admin_activation', { calls: writes(), toasts })
  })

  it('supprime un utilisateur après confirmation', async () => {
    await openPage()
    fireEvent.click(screen.getAllByRole('button', { name: "Supprimer l'utilisateur" })[1])
    const alert = await screen.findByRole('alertdialog')
    const question = within(alert).getAllByText(/./).map((el) => el.textContent)
    fireEvent.click(within(alert).getByRole('button', { name: 'Supprimer' }))
    await settle(() => toasts.length > 0)
    await golden('admin_suppression', { question, calls: writes(), toasts })
  })
})
