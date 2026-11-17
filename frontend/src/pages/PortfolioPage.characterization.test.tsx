import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { BOURSE, CROWDFUNDING, EMPTY_HISTORY, portfolioRoutes } from '@/test/portfolioFixtures'
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
const rows = () => screen.queryAllByRole('button', { name: /^Voir le détail de / }).map((row) => row.getAttribute('aria-label'))
const row = (symbol: string) => screen.getByRole('button', { name: `Voir le détail de ${symbol}` })

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/portfolio/${name}.json`)
}

async function open() {
  renderWithQuery(
    <MemoryRouter>
      <PortfolioPage />
    </MemoryRouter>
  )
  await settle(() => called('GET', '/dashboard/portfolio/p1/sparklines'))
  await screen.findByText('2 plateformes')
  await pause(50)
}

function platformCard(name: string) {
  const label = screen.getAllByText(name).find((el) => el.tagName === 'SPAN' && el.classList.contains('truncate'))
  fireEvent.click(label as HTMLElement)
}

async function chooseRowPlatform(symbol: string, platform: string) {
  const badge = within(row(symbol)).getAllByRole('button').find((b) => b.getAttribute('aria-haspopup') === 'dialog')
  fireEvent.click(badge as HTMLElement)
  fireEvent.click(await screen.findByRole('button', { name: platform }))
}

async function confirmDelete(trigger: HTMLElement) {
  fireEvent.click(trigger)
  const dialog = await screen.findByRole('alertdialog')
  const text = visibleText(dialog)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Supprimer' }))
  return text
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

describe('Portefeuille — positions', () => {
  it('affiche le premier portefeuille ordinaire et ses positions', async () => {
    await open()
    await golden('liste', { calls, toasts, rows: rows(), text: visibleText() })
  })

  it('filtre les positions par plateforme', async () => {
    await open()
    platformCard('Kraken')
    await pause(20)
    const kraken = { rows: rows(), text: visibleText() }
    platformCard('Kraken')
    await pause(20)
    await golden('filtre_plateforme', { kraken, reset: rows() })
  })

  it('déplie un actif détenu sur plusieurs plateformes', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Afficher les positions par plateforme de ETH' }))
    await pause(20)
    await golden('groupe_deplie', { text: visibleText() })
  })

  it('passe à un autre portefeuille', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Bourse' }))
    await screen.findByText('Aucun actif dans ce portefeuille')
    await pause(50)
    await golden('autre_portefeuille', { calls, text: visibleText() })
  })

  it('affiche les montants d’un utilisateur en dollars', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, preferredCurrency: 'USD' } })
    await open()
    await golden('devise_usd', { calls, text: visibleText() })
  })
})

describe('Portefeuille — détail d’un actif', () => {
  it('ouvre le détail d’une position et ses transactions', async () => {
    await open()
    fireEvent.click(row('BTC'))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByText('Achat')
    await pause(20)
    await golden('detail_position', { calls: calls.filter((c) => c.url === '/transactions'), text: visibleText(dialog) })
  })

  it('ouvre le détail d’un actif sur plusieurs plateformes', async () => {
    await open()
    fireEvent.click(row('ETH'))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('Transfert entrant')
    await pause(20)
    await golden('detail_groupe', { calls: calls.filter((c) => c.url === '/transactions'), text: visibleText(dialog) })
  })
})

describe('Portefeuille — plateforme d’une position', () => {
  it('change la plateforme', async () => {
    await open()
    await chooseRowPlatform('BTC', 'Ledger')
    await settle(() => toasts.length > 0 && count('GET', '/portfolios') > 1)
    await pause(50)
    await golden('plateforme_changee', { calls, toasts })
  })

  it('retire la plateforme', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Afficher les positions par plateforme de ETH' }))
    const kraken = await screen.findAllByRole('button', { name: /Kraken/ })
    fireEvent.click(kraken.find((b) => b.getAttribute('aria-haspopup') === 'dialog') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Retirer la plateforme' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('plateforme_retiree', { calls: calls.filter((c) => c.method === 'PATCH'), toasts })
  })

  it('signale un changement refusé', async () => {
    routes['PATCH /assets/a1'] = failure()
    await open()
    await chooseRowPlatform('BTC', 'Ledger')
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('plateforme_refusee', { calls, toasts })
  })
})

describe('Portefeuille — suppressions', () => {
  it('supprime une position après confirmation', async () => {
    await open()
    const dialog = await confirmDelete(within(row('SOL')).getByTitle('Supprimer'))
    await settle(() => toasts.length > 0 && count('GET', '/portfolios') > 1)
    await pause(50)
    await golden('position_supprimee', { dialog, calls, toasts })
  })

  it('signale une suppression de position refusée', async () => {
    routes['DELETE /assets/a4'] = failure()
    await open()
    await confirmDelete(within(row('SOL')).getByTitle('Supprimer'))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('position_refusee', { calls, toasts, text: visibleText() })
  })

  it('supprime le portefeuille et passe au suivant', async () => {
    routes['DELETE /portfolios/p1'] = () => {
      routes['GET /portfolios'] = ok([BOURSE, CROWDFUNDING])
      for (const key of Object.keys(routes).filter((k) => k.startsWith('GET /dashboard/portfolio/p1'))) delete routes[key]
      return { status: 204 }
    }
    await open()
    const dialog = await confirmDelete(screen.getByTitle('Supprimer le portefeuille'))
    await screen.findByText('Aucun actif dans ce portefeuille')
    await pause(50)
    await golden('portefeuille_supprime', { dialog, calls, toasts, text: visibleText() })
  })

  it('signale une suppression de portefeuille refusée', async () => {
    routes['DELETE /portfolios/p1'] = failure()
    await open()
    await confirmDelete(screen.getByTitle('Supprimer le portefeuille'))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('portefeuille_refuse', { calls, toasts })
  })
})

describe('Portefeuille — historique', () => {
  it('affiche les actifs vendus', async () => {
    await open()
    await openHistory()
    await golden('historique', { calls, text: visibleText() })
  })

  it('déplie puis filtre les actifs vendus', async () => {
    await open()
    await openHistory()
    fireEvent.click(screen.getByText('2 plateformes', { selector: 'span' }).closest('tr') as HTMLElement)
    await pause(20)
    const unfolded = visibleText()
    platformCard('Binance')
    await pause(20)
    await golden('historique_filtre', { unfolded, binance: visibleText() })
  })

  it('affiche un historique sans vente', async () => {
    routes['GET /dashboard/portfolio/p1/history'] = ok(EMPTY_HISTORY)
    await open()
    await openHistory()
    await golden('historique_vide', { text: visibleText() })
  })

  it('réagit à un historique indisponible', async () => {
    routes['GET /dashboard/portfolio/p1/history'] = failure()
    await open()
    await openHistory()
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('historique_erreur', { toasts, text: visibleText() })
  })
})

describe('Portefeuille — états', () => {
  it('réagit à des métriques indisponibles', async () => {
    routes['GET /dashboard/portfolio/p1'] = failure()
    renderWithQuery(
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    )
    await screen.findByText('Aucun actif dans ce portefeuille')
    await settle(() => toasts.length > 1)
    await pause(50)
    await golden('metriques_erreur', { calls, toasts, text: visibleText() })
  })

  it('réagit à une liste de portefeuilles indisponible', async () => {
    routes['GET /portfolios'] = failure()
    renderWithQuery(
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    )
    await screen.findByText('Impossible de charger le portefeuille')
    await pause(50)
    await golden('portefeuilles_erreur', { calls, toasts, text: visibleText() })
  })

  it('propose de créer un portefeuille quand seul le crowdfunding existe', async () => {
    routes['GET /portfolios'] = ok([CROWDFUNDING])
    renderWithQuery(
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    )
    await screen.findByText('Aucun portefeuille')
    await pause(50)
    await golden('aucun_portefeuille', { calls, text: visibleText() })
  })
})
