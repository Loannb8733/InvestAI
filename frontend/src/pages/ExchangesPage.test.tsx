import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ExchangesPage from './ExchangesPage'
import type { APIKey } from '@/types/exchanges'

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

function cle(surcharges: Partial<APIKey> = {}): APIKey {
  return {
    id: 'k1',
    exchange: 'binance',
    label: null,
    is_active: true,
    last_sync_at: '2026-09-01T10:00:00Z',
    last_error: null,
    created_at: '2026-01-01T00:00:00Z',
    ...surcharges,
  }
}

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


/**
 * ARC-07 — socle de rendu avant découpage.
 *
 * Le découpage de cette page (1 334 lignes, une seule fonction) était différé
 * faute de couverture : rien ne disait ce qu'elle affiche. Les tests d'erreur
 * ci-dessus en couvraient les deux échecs ; ceux-ci couvrent le rendu nominal,
 * c'est-à-dire ce qu'un déplacement de code ne doit pas faire disparaître.
 */
describe('ExchangesPage — rendu nominal (socle ARC-07)', () => {
  it('liste les plateformes connectées', async () => {
    listMock.mockResolvedValue([cle({ exchange: 'binance' }), cle({ id: 'k2', exchange: 'kraken' })])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    // « Binance » figure aussi dans la liste des plateformes supportées :
    // ce qui compte ici, c'est qu'il apparaisse **en plus** comme carte connectée.
    expect((await screen.findAllByText('Binance')).length).toBeGreaterThan(1)
    expect(screen.getAllByText('Kraken').length).toBeGreaterThan(1)
  })

  it("affiche le libellé d'une clé quand il existe", async () => {
    listMock.mockResolvedValue([cle({ label: 'Compte principal' })])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    expect(await screen.findByText('Compte principal')).toBeInTheDocument()
  })

  it('signale une clé en erreur', async () => {
    listMock.mockResolvedValue([cle({ is_active: false, last_error: 'Clé révoquée' })])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    await screen.findAllByText('Binance')
    expect(screen.getByText(/révoquée/i)).toBeInTheDocument()
  })

  it('propose de connecter une plateforme quand aucune ne l\'est', async () => {
    listMock.mockResolvedValue([])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    // Le bouton d'ajout reste offert : une page sans clé n'est pas une impasse.
    const boutons = await screen.findAllByRole('button', { name: /ajouter|connecter|nouvelle/i })
    expect(boutons.length).toBeGreaterThan(0)
  })

  it('ouvre la confirmation avant de supprimer une connexion', async () => {
    // Le dialogue est un composant à part depuis ARC-07 : ce test vérifie que
    // la page l'ouvre encore. Sans lui, forcer sa cible à `null` ne faisait
    // tomber aucun test — vérifié par canari avant de l'écrire.
    listMock.mockResolvedValue([cle({ exchange: 'binance', label: 'Compte principal' })])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    await screen.findAllByText('Binance')
    fireEvent.click(screen.getByRole('button', { name: /suppr/i }))

    expect(await screen.findByText(/Supprimer cette connexion/i)).toBeInTheDocument()
    // Le texte rassure sur ce qui ne disparaît pas : c'est le sens du dialogue.
    expect(screen.getByText(/resteront dans l'application/i)).toBeInTheDocument()
  })

  it('rend les sections permanentes de la page', async () => {
    listMock.mockResolvedValue([cle()])
    listExchangesMock.mockResolvedValue(EXCHANGES)
    renderWithProviders()

    await screen.findAllByText('Binance')
    // Ce bloc ne dépend pas des données : il doit survivre au découpage.
    expect(screen.getByText(/exchanges supportés/i)).toBeInTheDocument()
  })
})
