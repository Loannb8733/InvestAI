import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { formatCurrency } from '@/lib/utils'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { BOURSE, CROWDFUNDING, CRYPTO_METRICS, portfolioRoutes } from '@/test/portfolioFixtures'
import { renderWithQuery, settle } from '@/test/render'
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
const failure = (status = 500) => () => ({ status, data: { detail: 'boom' } })
const called = (method: string, url: string) => calls.some((c) => c.method === method && c.url === url)
const count = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url).length
const listDetail = [{ type: 'too_long', loc: ['body', 'symbol'], msg: 'String should have at most 20 characters' }]
const money = (value: number, currency?: string) => formatCurrency(value, currency).replace(/\s+/g, ' ')
const page = (root?: HTMLElement) => visibleText(root).join(' | ')
const row = (symbol: string) => screen.getByRole('button', { name: `Voir le détail de ${symbol}` })

function show() {
  renderWithQuery(
    <MemoryRouter>
      <PortfolioPage />
    </MemoryRouter>
  )
}

async function open() {
  show()
  await settle(() => called('GET', '/dashboard/portfolio/p1/sparklines'))
  await screen.findByText('2 plateformes')
  await pause(50)
}

async function changeBtcPlatform() {
  const badge = within(row('BTC')).getAllByRole('button').find((b) => b.getAttribute('aria-haspopup') === 'dialog')
  fireEvent.click(badge as HTMLElement)
  fireEvent.click(await screen.findByRole('button', { name: 'Ledger' }))
}

async function confirmDelete(trigger: HTMLElement) {
  fireEvent.click(trigger)
  const dialog = await screen.findByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Supprimer' }))
}

async function openHistory() {
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Historique' }))
  await settle(() => called('GET', '/dashboard/portfolio/p1/history'))
  await pause(50)
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

describe('portefeuille — défauts corrigés', () => {
  it('affiche les montants dans la devise de l’utilisateur', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, preferredCurrency: 'USD' } })
    await open()
    const text = page()
    expect(text).toContain(money(40510, 'USD'))
    expect(text).not.toContain(money(40510))
  })

  it('compte le cash saisi en euros une fois converti dans la devise de l’utilisateur', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, preferredCurrency: 'USD' } })
    routes['GET /dashboard/portfolio/p1'] = ok({ ...CRYPTO_METRICS, cash_from_balances: 132.55 })
    await open()
    const text = page()
    expect(text).toContain(money(332.55, 'USD'))
    expect(text).toContain(`Binance | : | ${money(120.5)}`)
  })

  it('ne retire pas une seconde fois les frais du P&L d’une plateforme', async () => {
    await open()
    expect(page()).toContain(money(17930))
  })

  it('signale une écriture refusée par une seule notification', async () => {
    routes['PATCH /assets/a1'] = failure()
    await open()
    await changeBtcPlatform()
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts).toHaveLength(1)
  })

  it('donne un message lisible à un 422 dont le détail est une liste', async () => {
    routes['POST /assets/check'] = () => ({ status: 422, data: { detail: listDetail } })
    await expect(http.post('/assets/check', {})).rejects.toBeTruthy()
    routes['POST /assets'] = () => ({ status: 422, data: { detail: listDetail } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter un actif' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(document.getElementById('symbol') as HTMLInputElement, { target: { value: 'BTC' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 1)
    expect(toasts.every((t) => typeof t.description === 'string')).toBe(true)
  })

  it('montre un état d’erreur quand les positions ne chargent pas', async () => {
    routes['GET /dashboard/portfolio/p1'] = failure()
    show()
    await screen.findByText('Impossible de charger les positions')
    await pause(50)
    expect(screen.queryByText('Aucun actif dans ce portefeuille')).toBeNull()
    expect(toasts).toHaveLength(0)
  })

  it('montre un état d’erreur quand l’historique ne charge pas', async () => {
    routes['GET /dashboard/portfolio/p1/history'] = failure()
    await open()
    await openHistory()
    await screen.findByText("Impossible de charger l'historique")
    expect(screen.queryByText('Aucune donnée historique')).toBeNull()
    expect(toasts).toHaveLength(0)
  })

  it('n’ajoute aucune notification à l’état d’erreur de la liste', async () => {
    routes['GET /portfolios'] = failure()
    show()
    await screen.findByText('Impossible de charger le portefeuille')
    await pause(50)
    expect(toasts).toHaveLength(0)
  })

  it('ne relit pas le portefeuille supprimé', async () => {
    routes['DELETE /portfolios/p1'] = () => {
      routes['GET /portfolios'] = ok([BOURSE, CROWDFUNDING])
      return { status: 204 }
    }
    await open()
    const before = count('GET', '/dashboard/portfolio/p1')
    await confirmDelete(screen.getByTitle('Supprimer le portefeuille'))
    await screen.findByText('Aucun actif dans ce portefeuille')
    await pause(50)
    expect(count('GET', '/dashboard/portfolio/p1')).toBe(before)
    expect(toasts.map((t) => t.title)).toEqual(['Portefeuille supprimé'])
  })

  it('écrit les nombres au format français', async () => {
    await open()
    fireEvent.click(screen.getByText('Cash disponible'))
    const dialog = await screen.findByRole('dialog')
    const text = `${page()} | ${page(dialog)}`
    for (const expected of ['0,50000000', '+99,2 %', '+85,2 %/an', '40,5 %', '540,12', money(120.5)]) {
      expect(text).toContain(expected)
    }
    for (const unexpected of ['0.50000000', '99.2%', '40.5%', '540.12', '120.50 €']) {
      expect(text).not.toContain(unexpected)
    }
  })

  it('ne pose pas de second titre principal sur l’état vide', async () => {
    routes['GET /portfolios'] = ok([CROWDFUNDING])
    show()
    await screen.findByText('Aucun portefeuille')
    expect(screen.queryAllByRole('heading', { level: 1 })).toHaveLength(0)
  })

  it('ne recharge pas la liste fixe des formats CSV après une écriture', async () => {
    await open()
    await changeBtcPlatform()
    await settle(() => toasts.length > 0 && count('GET', '/portfolios') > 1)
    await pause(50)
    expect(count('GET', '/transactions/csv-platforms')).toBe(1)
  })
})
