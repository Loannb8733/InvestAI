import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { http } from '@/shared/api/http'
import { createFakeServer, ok } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { BOURSE, CROWDFUNDING, CRYPTO, portfolioRoutes } from '@/test/portfolioFixtures'
import { renderWithQuery } from '@/test/render'
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
const called = (method: string, url: string) => calls.some((c) => c.method === method && c.url === url)

function show() {
  renderWithQuery(
    <MemoryRouter>
      <PortfolioPage />
    </MemoryRouter>
  )
}

async function exportButtonReady() {
  await waitFor(() => expect(called('GET', '/dashboard/portfolio/p1')).toBe(true))
  return screen.getByRole('button', { name: /Exporter CSV/i })
}

beforeAll(() => {
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(portfolioRoutes())
  routes['GET /portfolios'] = ok([CRYPTO])
  toasts.length = 0
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  http.defaults.adapter = server.adapter
  vi.restoreAllMocks()
})

describe('les états de la page', () => {
  it('montre un squelette tant que les portefeuilles arrivent', () => {
    http.defaults.adapter = () => new Promise(() => {})
    show()

    expect(screen.getByText(/ligne par ligne/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Exporter CSV/i })).not.toBeInTheDocument()
  })

  it("affiche une erreur rattrapable plutôt qu'une page vide", async () => {
    routes['GET /portfolios'] = () => ({ status: 500, data: { detail: 'réseau' } })
    show()

    expect(await screen.findByText(/Impossible de charger le portefeuille/i)).toBeInTheDocument()
  })

  it('propose de créer un portefeuille quand il n’y en a aucun', async () => {
    routes['GET /portfolios'] = ok([])
    show()

    expect(await screen.findByText('Aucun portefeuille')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Exporter CSV/i })).not.toBeInTheDocument()
  })

  it('affiche la page une fois les portefeuilles chargés', async () => {
    show()

    expect(await screen.findByRole('button', { name: /Exporter CSV/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Portefeuille', level: 2 })).toBeInTheDocument()
  })
})

describe('le choix du portefeuille', () => {
  it('écarte le portefeuille de crowdfunding, qui a sa propre page', async () => {
    routes['GET /portfolios'] = ok([CRYPTO, { ...CROWDFUNDING, name: 'Crowdfunding' }])
    show()

    await screen.findByRole('button', { name: 'Crypto' })
    expect(screen.queryByRole('button', { name: 'Crowdfunding' })).not.toBeInTheDocument()
  })

  it('l’écarte même s’il a été renommé', async () => {
    routes['GET /portfolios'] = ok([CRYPTO, CROWDFUNDING])
    show()

    await screen.findByRole('button', { name: 'Crypto' })
    expect(screen.queryByRole('button', { name: 'Mes prêts' })).not.toBeInTheDocument()
  })

  it('l’écarte encore par son nom quand la réponse ne porte pas de marqueur', async () => {
    routes['GET /portfolios'] = ok([CRYPTO, { ...CROWDFUNDING, name: 'crowdfunding', kind: null }])
    show()

    await screen.findByRole('button', { name: 'Crypto' })
    expect(screen.queryByRole('button', { name: /^crowdfunding$/i })).not.toBeInTheDocument()
  })

  it('sélectionne le premier portefeuille sans attendre un clic', async () => {
    routes['GET /portfolios'] = ok([CRYPTO, BOURSE])
    show()

    await waitFor(() => expect(called('GET', '/dashboard/portfolio/p1')).toBe(true))
  })

  it('charge les métriques du portefeuille choisi', async () => {
    routes['GET /portfolios'] = ok([CRYPTO, BOURSE])
    show()
    await waitFor(() => expect(called('GET', '/dashboard/portfolio/p1')).toBe(true))

    fireEvent.click(screen.getByRole('button', { name: 'Bourse' }))

    await waitFor(() => expect(called('GET', '/dashboard/portfolio/p2')).toBe(true))
  })

  it("ne demande l'historique qu'une fois son onglet ouvert", async () => {
    show()
    await screen.findByRole('button', { name: /Exporter CSV/i })

    expect(called('GET', '/dashboard/portfolio/p1/history')).toBe(false)
  })
})

describe("l'export CSV", () => {
  beforeEach(() => {
    routes['GET /transactions/export-csv'] = ok('symbol,type\n')
    Object.defineProperty(window.URL, 'createObjectURL', { value: vi.fn(() => 'blob:faux'), writable: true })
    Object.defineProperty(window.URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
  })

  it('exporte les transactions du portefeuille affiché', async () => {
    show()

    fireEvent.click(await exportButtonReady())

    await waitFor(() => expect(toasts.at(-1)?.title).toBe('Export réussi'))
    expect(calls.find((c) => c.url === '/transactions/export-csv')?.params).toEqual({ portfolio_id: 'p1' })
  })

  it("libère l'URL du fichier après le téléchargement", async () => {
    show()

    fireEvent.click(await exportButtonReady())

    await waitFor(() => expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:faux'))
  })

  it("signale l'échec au lieu de laisser croire au succès", async () => {
    routes['GET /transactions/export-csv'] = () => ({ status: 500, data: { detail: 'serveur' } })
    show()

    fireEvent.click(await exportButtonReady())

    await waitFor(() => expect(toasts.at(-1)?.description).toBe("Impossible d'exporter les transactions."))
    expect(toasts.at(-1)?.variant).toBe('destructive')
    expect(window.URL.createObjectURL).not.toHaveBeenCalled()
  })
})
