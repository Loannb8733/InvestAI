import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ExchangesPage from './ExchangesPage'

/**
 * UX-04 — deux requêtes, deux portées d'erreur.
 *
 * `apiKeysApi.list` porte le contenu de la page : sans elle, il n'y a rien à
 * montrer. `isLoading` retombant à false en cas d'échec, la page se rendait
 * vide — impossible de distinguer « aucune clé enregistrée » de « l'API est
 * tombée », et aucun moyen de réessayer.
 *
 * `apiKeysApi.listExchanges` ne sert qu'à lister les plateformes connectables.
 * Son échec empêche d'en ajouter une, mais les clés déjà enregistrées restent
 * consultables et synchronisables : l'erreur reste donc cantonnée à sa carte.
 * Étendre l'état d'erreur à la page entière priverait l'utilisateur de ses
 * propres clés pour une liste de référence indisponible.
 *
 * Ces tests sont aussi le socle qui manquait à ARC-07 : le découpage de cette
 * page a été différé faute de couverture de rendu.
 */

const listMock = vi.hoisted(() => vi.fn())
const listExchangesMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  apiKeysApi: {
    list: listMock,
    listExchanges: listExchangesMock,
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
    sync: vi.fn(),
    refreshFx: vi.fn(),
    importHistoryAsync: vi.fn(),
    getImportStatus: vi.fn(),
  },
  transactionsApi: {
    balanceGaps: vi.fn().mockResolvedValue({ gaps: [] }),
    creditBalanceGaps: vi.fn(),
  },
}))

vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('@/components/exchanges/ColdWalletsManager', () => ({ default: () => null }))
vi.mock('@/lib/invalidate-queries', () => ({ invalidateAllFinancialData: vi.fn() }))

const EXCHANGES = [
  { id: 'binance', name: 'Binance', description: 'Exchange', requires_secret: true, requires_passphrase: false },
  { id: 'kraken', name: 'Kraken', description: 'Exchange', requires_secret: true, requires_passphrase: false },
]

function renderWithProviders() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExchangesPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  listMock.mockReset()
  listExchangesMock.mockReset()
})

afterEach(() => {
  listMock.mockResolvedValue([])
  listExchangesMock.mockResolvedValue(EXCHANGES)
})

describe('ExchangesPage — échec du chargement des clés (UX-04)', () => {
  it('affiche un état d\'erreur au lieu d\'une page vide', async () => {
    listMock.mockRejectedValue(new Error('500'))
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()
    expect(await screen.findByText('Impossible de charger vos clés API')).toBeInTheDocument()
  })

  it('propose de réessayer', async () => {
    listMock.mockRejectedValue(new Error('500'))
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()
    expect(await screen.findByRole('button', { name: /réessayer/i })).toBeInTheDocument()
  })

  it('n\'affiche pas d\'erreur quand le chargement aboutit', async () => {
    listMock.mockResolvedValue([])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()
    await screen.findByText('Exchanges supportés')
    expect(screen.queryByText('Impossible de charger vos clés API')).not.toBeInTheDocument()
  })
})

describe('ExchangesPage — échec de la liste des plateformes (UX-04)', () => {
  it('cantonne l\'erreur à sa carte, sans masquer la page', async () => {
    listMock.mockResolvedValue([])
    listExchangesMock.mockRejectedValue(new Error('500'))
    renderWithProviders()

    expect(await screen.findByText('Liste des plateformes indisponible')).toBeInTheDocument()
    // Le reste de la page doit survivre : c'est là que vivent les clés déjà
    // enregistrées, leur synchronisation et leur suppression.
    expect(screen.queryByText('Impossible de charger vos clés API')).not.toBeInTheDocument()
    expect(screen.getByText('Exchanges supportés')).toBeInTheDocument()
  })

  it('ne signale rien quand la liste se charge', async () => {
    listMock.mockResolvedValue([])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()
    await screen.findByText('Exchanges supportés')
    expect(screen.queryByText('Liste des plateformes indisponible')).not.toBeInTheDocument()
  })
})
