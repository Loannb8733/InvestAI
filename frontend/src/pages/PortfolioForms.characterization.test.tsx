import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { CROWDFUNDING, portfolioRoutes } from '@/test/portfolioFixtures'
import { chooseOption, renderWithQuery, settle } from '@/test/render'
import PortfolioPage from './PortfolioPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const writes = () => calls.filter((c) => c.method !== 'GET')
const reads = () => calls.filter((c) => c.method === 'GET').map((c) => c.url)
const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/portfolio/${name}.json`)
}

async function open() {
  renderWithQuery(
    <MemoryRouter>
      <PortfolioPage />
    </MemoryRouter>
  )
  await screen.findByText('2 plateformes')
  await pause(30)
}

async function dialogFor(button: string) {
  fireEvent.click(screen.getByRole('button', { name: button }))
  return screen.findByRole('dialog')
}

async function afterWrite(predicate: () => boolean) {
  await settle(predicate)
  await pause(50)
  return { writes: writes(), reads: reads() }
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(portfolioRoutes())
  toasts.length = 0
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Nouveau portefeuille', () => {
  it('crée un portefeuille', async () => {
    await open()
    const dialog = await dialogFor('Nouveau portefeuille')
    const text = visibleText(dialog)
    calls.length = 0
    type('name', 'PEA')
    type('description', 'Actions européennes')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('portefeuille_cree', { text, calls, toasts, open: screen.queryByRole('dialog') !== null })
  })

  it('crée le premier portefeuille depuis l’état vide', async () => {
    routes['GET /portfolios'] = ok([CROWDFUNDING])
    renderWithQuery(
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Créer un portefeuille' }))
    const dialog = await screen.findByRole('dialog')
    type('name', 'Crypto')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('premier_portefeuille', { writes: writes(), toasts })
  })

  it('exige un nom', async () => {
    await open()
    const dialog = await dialogFor('Nouveau portefeuille')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await within(dialog).findByText('Nom requis')
    await golden('portefeuille_sans_nom', { writes: writes(), text: visibleText(dialog) })
  })

  it('signale une création refusée', async () => {
    routes['POST /portfolios'] = () => ({ status: 400, data: { detail: 'Nom déjà utilisé' } })
    await open()
    const dialog = await dialogFor('Nouveau portefeuille')
    type('name', 'Crypto')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('portefeuille_refuse_creation', { writes: writes(), toasts })
  })
})

describe('Ajout d’un actif', () => {
  it('ajoute une crypto sur une plateforme', async () => {
    await open()
    const dialog = await dialogFor('Ajouter un actif')
    const text = visibleText(dialog)
    type('symbol', 'link')
    type('name', 'Chainlink')
    type('quantity', '12.5')
    type('avg_buy_price', '14.2')
    fireEvent.click(within(dialog).getByRole('combobox', { name: 'Où est stocké cet actif ?' }))
    fireEvent.click(await screen.findByRole('option', { name: /Boursorama/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('actif_ajoute', { text, writes: writes(), toasts, open: screen.queryByRole('dialog') !== null })
  })

  it('ajoute un bien immobilier', async () => {
    await open()
    const dialog = await dialogFor('Ajouter un actif')
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Immobilier')
    await within(dialog).findByLabelText('Nom du projet')
    const text = visibleText(dialog)
    type('project_name', 'Résidence Étoile — Lyon 3e arrondissement')
    type('invested_amount', '2000')
    type('interest_rate', '9.5')
    type('maturity_date', '2027-06-30')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('bien_immobilier_ajoute', { text, writes: writes(), toasts })
  })

  it('valide les champs d’un actif', async () => {
    await open()
    const dialog = await dialogFor('Ajouter un actif')
    type('quantity', '-1')
    type('avg_buy_price', '-2')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await within(dialog).findByText('Symbole requis')
    const crypto = visibleText(dialog)
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Immobilier')
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Ajouter' }))
    await within(dialog).findByText('Nom du projet requis')
    await golden('actif_invalide', { writes: writes(), crypto, realEstate: visibleText(dialog) })
  })

  it('signale un ajout refusé', async () => {
    routes['POST /assets'] = () => ({ status: 400, data: { detail: 'Actif déjà présent' } })
    await open()
    const dialog = await dialogFor('Ajouter un actif')
    type('symbol', 'BTC')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('actif_refuse', { writes: writes(), toasts })
  })

  it('signale un ajout rejeté par la validation du serveur', async () => {
    const detail = [{ type: 'too_long', loc: ['body', 'symbol'], msg: 'String should have at most 20 characters' }]
    routes['POST /assets'] = () => ({ status: 422, data: { detail } })
    await open()
    const dialog = await dialogFor('Ajouter un actif')
    type('symbol', 'BTC')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('actif_rejete_422', { toasts })
  })
})

describe('Cash disponible', () => {
  async function openCash() {
    await open()
    fireEvent.click(screen.getByText('Cash disponible'))
    return screen.findByRole('dialog')
  }

  function submit(dialog: HTMLElement) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter / Modifier' }))
  }

  it('enregistre un solde sur une plateforme', async () => {
    const dialog = await openCash()
    const text = visibleText(dialog)
    calls.length = 0
    chooseOption(within(dialog).getByRole('combobox'), 'Kraken')
    type('amount', '300')
    submit(dialog)
    const refetched = await afterWrite(() => toasts.length > 0)
    await golden('cash_enregistre', { text, refetched, toasts, amount: field('amount').value })
  })

  it('enregistre un solde sur une autre plateforme', async () => {
    const dialog = await openCash()
    chooseOption(within(dialog).getByRole('combobox'), 'Autre')
    type('customExchange', 'Boursorama')
    type('amount', '50.25')
    submit(dialog)
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('cash_autre_plateforme', { writes: writes(), toasts })
  })

  it('refuse un solde sans plateforme ou négatif', async () => {
    const dialog = await openCash()
    type('amount', '10')
    submit(dialog)
    chooseOption(within(dialog).getByRole('combobox'), 'Kraken')
    type('amount', '-5')
    submit(dialog)
    await pause(30)
    await golden('cash_invalide', { writes: writes(), toasts })
  })

  it('supprime un solde', async () => {
    const dialog = await openCash()
    calls.length = 0
    fireEvent.click(within(dialog).getByRole('button', { name: 'Supprimer ce solde' }))
    const refetched = await afterWrite(() => toasts.length > 0)
    await golden('cash_supprime', { refetched, toasts })
  })

  it('signale un solde refusé', async () => {
    routes['PUT /portfolios/p1/cash-balance'] = () => ({ status: 500, data: { detail: 'boom' } })
    const dialog = await openCash()
    chooseOption(within(dialog).getByRole('combobox'), 'Kraken')
    type('amount', '300')
    submit(dialog)
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('cash_refuse', { writes: writes(), toasts })
  })
})
