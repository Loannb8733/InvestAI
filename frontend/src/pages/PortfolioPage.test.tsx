import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PortfolioPage from './PortfolioPage'

/**
 * La page qui montre les 56 actifs, ligne par ligne.
 *
 * 759 lignes, **0 %** de couverture. C'est la vue centrale du produit : les
 * autres pages sans test — objectifs, notes, alertes, simulations — portent des
 * fonctionnalités dont la base ne contient aucun enregistrement ; celle-ci
 * affiche tout ce que l'utilisateur possède.
 *
 * Le filet porte sur la charpente : les quatre états de chargement, le
 * portefeuille masqué, la sélection automatique, et l'export CSV — le seul
 * geste de la page qui écrit un fichier sur le poste.
 */

const listerPortefeuilles = vi.hoisted(() => vi.fn())
const metriques = vi.hoisted(() => vi.fn())
const historique = vi.hoisted(() => vi.fn())
const sparklines = vi.hoisted(() => vi.fn())
const exporterCSV = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  portfoliosApi: { list: listerPortefeuilles, delete: vi.fn(), create: vi.fn() },
  dashboardApi: {
    getPortfolioMetrics: metriques,
    getPortfolioHistory: historique,
    getPortfolioSparklines: sparklines,
  },
  assetsApi: { delete: vi.fn(), update: vi.fn(), list: vi.fn(), create: vi.fn() },
  // `getCSVPlatforms` alimente une requête montée par le formulaire d'import :
  // rendre `undefined` la ferait échouer bruyamment sans rien apprendre.
  transactionsApi: {
    exportCSV: exporterCSV,
    create: vi.fn(),
    getCSVPlatforms: vi.fn().mockResolvedValue({ platforms: [] }),
    importCSV: vi.fn(),
  },
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/lib/invalidate-queries', () => ({ invalidateAllFinancialData: vi.fn() }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selecteur: (e: unknown) => unknown) => selecteur({ user: { preferredCurrency: 'EUR' } }),
}))

const CRYPTO = { id: 'p-crypto', name: 'Crypto', total_value: 100000 }
const CROWDFUNDING = { id: 'p-cf', name: 'Crowdfunding', total_value: 6000 }

const METRIQUES_VIDES = {
  total_value: 0,
  total_invested: 0,
  total_gain_loss: 0,
  total_gain_loss_percent: 0,
  assets: [],
  allocation: [],
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  listerPortefeuilles.mockResolvedValue([CRYPTO])
  metriques.mockResolvedValue(METRIQUES_VIDES)
  historique.mockResolvedValue({
    total_invested_all_time: 0,
    total_sold: 0,
    total_fees: 0,
    realized_gains: 0,
    current_holdings_count: 0,
    sold_assets_count: 0,
    sold_assets: [],
  })
  sparklines.mockResolvedValue([])
})

describe('les états de la page', () => {
  it('montre un squelette tant que les portefeuilles arrivent', () => {
    listerPortefeuilles.mockReturnValue(new Promise(() => {}))
    afficher()

    expect(screen.getByText(/ligne par ligne/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Exporter CSV/i })).not.toBeInTheDocument()
  })

  it("affiche une erreur rattrapable plutôt qu'une page vide", async () => {
    // Une requête rejetée ne lève rien pendant le rendu : sans cet état, la
    // frontière d'erreur de la route ne la voit pas et l'écran reste blanc.
    listerPortefeuilles.mockRejectedValue(new Error('réseau'))
    afficher()

    expect(await screen.findByText(/Impossible de charger le portefeuille/i)).toBeInTheDocument()
  })

  it('propose de créer un portefeuille quand il n’y en a aucun', async () => {
    listerPortefeuilles.mockResolvedValue([])
    afficher()

    await waitFor(() => expect(listerPortefeuilles).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /Exporter CSV/i })).not.toBeInTheDocument()
  })

  it('affiche la page une fois les portefeuilles chargés', async () => {
    afficher()

    expect(await screen.findByRole('button', { name: /Exporter CSV/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Portefeuille', level: 2 })).toBeInTheDocument()
  })
})

describe('le choix du portefeuille', () => {
  it('écarte le portefeuille de crowdfunding, qui a sa propre page', async () => {
    listerPortefeuilles.mockResolvedValue([CRYPTO, CROWDFUNDING])
    afficher()

    await screen.findByRole('button', { name: 'Crypto' })
    expect(screen.queryByRole('button', { name: 'Crowdfunding' })).not.toBeInTheDocument()
  })

  it('écarte le portefeuille quelle que soit la casse de son nom', async () => {
    // Le filtre compare en minuscules ; le serveur, lui, cherche « Crowdfunding »
    // à la casse exacte (voir NEW-68). Ce test épingle la règle de l'écran.
    listerPortefeuilles.mockResolvedValue([CRYPTO, { ...CROWDFUNDING, name: 'crowdfunding' }])
    afficher()

    await screen.findByRole('button', { name: 'Crypto' })
    expect(screen.queryByRole('button', { name: /^crowdfunding$/i })).not.toBeInTheDocument()
  })

  it('sélectionne le premier portefeuille sans attendre un clic', async () => {
    listerPortefeuilles.mockResolvedValue([CRYPTO, { id: 'p-2', name: 'Bourse', total_value: 5000 }])
    afficher()

    await waitFor(() => expect(metriques).toHaveBeenCalledWith('p-crypto'))
  })

  it('charge les métriques du portefeuille choisi', async () => {
    listerPortefeuilles.mockResolvedValue([CRYPTO, { id: 'p-2', name: 'Bourse', total_value: 5000 }])
    afficher()
    await waitFor(() => expect(metriques).toHaveBeenCalledWith('p-crypto'))

    fireEvent.click(screen.getByRole('button', { name: 'Bourse' }))

    await waitFor(() => expect(metriques).toHaveBeenCalledWith('p-2'))
  })

  it("ne demande l'historique qu'une fois son onglet ouvert", async () => {
    // Il est plus lourd que les métriques : le charger d'emblée ralentirait
    // l'affichage de la page pour un onglet que l'utilisateur n'ouvre pas.
    afficher()
    await screen.findByRole('button', { name: /Exporter CSV/i })

    expect(historique).not.toHaveBeenCalled()
  })
})

describe("l'export CSV", () => {
  beforeEach(() => {
    Object.defineProperty(window.URL, 'createObjectURL', { value: vi.fn(() => 'blob:faux'), writable: true })
    Object.defineProperty(window.URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
  })

  it('exporte les transactions du portefeuille affiché', async () => {
    exporterCSV.mockResolvedValue(new Blob(['symbol,type\n']))
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /Exporter CSV/i }))

    await waitFor(() => expect(exporterCSV).toHaveBeenCalledWith('p-crypto'))
    expect(toastMock.mock.calls.at(-1)![0].title).toBe('Export réussi')
  })

  it("libère l'URL du fichier après le téléchargement", async () => {
    // Sans quoi le contenu reste en mémoire pour toute la durée de l'onglet.
    exporterCSV.mockResolvedValue(new Blob(['symbol,type\n']))
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /Exporter CSV/i }))

    await waitFor(() => expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:faux'))
  })

  it("signale l'échec au lieu de laisser croire au succès", async () => {
    exporterCSV.mockRejectedValue(new Error('serveur'))
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /Exporter CSV/i }))

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.variant).toBe('destructive')
    expect(window.URL.createObjectURL).not.toHaveBeenCalled()
  })
})
