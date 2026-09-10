import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardPage from './DashboardPage'

/**
 * Le tableau de bord crypto — 965 lignes, **0 %**.
 *
 * C'est la page qui porte le panneau « Transactions récentes » corrigé par
 * NEW-64 : le serveur triait sur une date d'exécution absente sur 195 des 840
 * lignes, et PostgreSQL plaçant les valeurs nulles en tête, l'écran n'a jamais
 * montré un mouvement récent. Le correctif est côté serveur ; ce filet vérifie
 * que l'écran affiche bien ce qu'on lui donne, dans l'ordre reçu.
 *
 * Le reste porte sur la charpente et sur le **mode confidentialité**, dont la
 * promesse est particulière : un montant qui échapperait au masquage se
 * montrerait à quelqu'un qui se croit protégé.
 */

const obtenirMetriques = vi.hoisted(() => vi.fn())
const obtenirBenchmarks = vi.hoisted(() => vi.fn())
const tableauCrowdfunding = vi.hoisted(() => vi.fn())
const pageVisible = vi.hoisted(() => ({ valeur: true }))

// Mock partiel : les panneaux du tableau de bord importent une dizaine d'autres
// exports du module (`reportsApi`, `investorProfileQueryKey`…). Les omettre fait
// échouer leur rendu par une erreur qui n'a rien à voir avec ce qu'on éprouve.
vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  dashboardApi: { getMetrics: obtenirMetriques, getBenchmarks: obtenirBenchmarks },
  crowdfundingApi: { getDashboard: tableauCrowdfunding },
}))
vi.mock('@/hooks/useRealtimePrices', () => ({
  useRealtimePrices: () => ({ prices: {}, connected: false }),
}))
vi.mock('@/hooks/usePageVisibility', () => ({ usePageVisibility: () => pageVisible.valeur }))
vi.mock('@/hooks/useExportPdf', () => ({ useExportPdf: () => ({ exportToPdf: vi.fn() }) }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selecteur: (e: unknown) => unknown) => selecteur({ user: { preferredCurrency: 'EUR' } }),
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))

const TRANSACTIONS = [
  { id: 't1', symbol: 'BTC', asset_type: 'crypto', transaction_type: 'buy', quantity: 0.5, price: 30000, total: 15000, executed_at: '2026-09-08T10:00:00Z' },
  { id: 't2', symbol: 'ETH', asset_type: 'crypto', transaction_type: 'sell', quantity: 2, price: 2000, total: 4000, executed_at: '2026-09-07T10:00:00Z' },
]

function metriques(surcharge: Record<string, unknown> = {}) {
  return {
    total_value: 123456,
    total_invested: 100000,
    net_gain_loss: 23456,
    net_gain_loss_percent: 23.4,
    available_liquidity: 5000,
    asset_allocation: [],
    recent_transactions: TRANSACTIONS,
    active_alerts: [],
    upcoming_events: [],
    index_comparison: [],
    historical_data: [],
    currency_exposure: [],
    top_performers: [],
    worst_performers: [],
    allocation: [],
    assets_count: 12,
    portfolios_count: 2,
    net_capital: 100000,
    period_twr_percent: 5.2,
    roi_annualized: 12.3,
    forex_stale: false,
    last_updated: '2026-09-09T12:00:00Z',
    earn_summary: null,
    advanced_metrics: null,
    total_dividend_income: 0,
    total_return: 23456,
    ...surcharge,
  }
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  pageVisible.valeur = true
  obtenirMetriques.mockResolvedValue(metriques())
  obtenirBenchmarks.mockResolvedValue([])
  tableauCrowdfunding.mockResolvedValue({ total_invested: 0, projects_count: 0 })
})

describe('les états de la page', () => {
  it('montre un squelette tant que les métriques arrivent', () => {
    obtenirMetriques.mockReturnValue(new Promise(() => {}))
    afficher()

    expect(screen.queryByText(/Transactions récentes/i)).not.toBeInTheDocument()
  })

  it('propose de réessayer quand le premier chargement échoue', async () => {
    obtenirMetriques.mockRejectedValue(new Error('réseau'))
    afficher()

    expect(await screen.findByText(/Impossible de charger le tableau de bord/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Réessayer/i })).toBeInTheDocument()
  })

  it('survit à un échec de rechargement en gardant les données précédentes', async () => {
    // Le rafraîchissement tourne toutes les soixante secondes : une coupure
    // passagère ne doit pas remplacer un tableau de bord parfaitement
    // affichable par un message d'erreur. C'est ce que `keepPreviousData`
    // apporte, et la garde d'erreur plein écran est conditionnée à `!metrics`
    // précisément pour ne pas l'annuler.
    afficher()
    await screen.findByText(/Transactions récentes/i)

    obtenirMetriques.mockRejectedValue(new Error('coupure passagère'))
    fireEvent.click(screen.getByRole('button', { name: '24h' }))

    await waitFor(() => expect(obtenirMetriques).toHaveBeenCalledWith(1))
    expect(screen.getByText(/Transactions récentes/i)).toBeInTheDocument()
    expect(screen.queryByText(/Impossible de charger/i)).not.toBeInTheDocument()
  })
})

describe('le panneau des transactions récentes', () => {
  it('affiche les lignes dans l’ordre reçu du serveur', async () => {
    // L'écran ne retrie pas : c'est le serveur qui décide de l'ordre, et c'est
    // là que NEW-64 a été corrigé. Retrier ici masquerait une régression.
    afficher()
    await screen.findByText(/Transactions récentes/i)

    const btc = screen.getByText('BTC')
    const eth = screen.getByText('ETH')
    expect(btc.compareDocumentPosition(eth) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('distingue une entrée d’une sortie par son signe', async () => {
    // Un achat ajoute, une vente retire : le signe est la seule chose qui les
    // sépare à l'œil dans ce panneau.
    afficher()
    await screen.findByText(/Transactions récentes/i)

    const montants = Array.from(document.querySelectorAll('p')).map((n) => n.textContent ?? '')
    expect(montants.some((t) => t.startsWith('+') && t.includes('15'))).toBe(true)
    expect(montants.some((t) => t.startsWith('-') && t.includes('4'))).toBe(true)
  })

  it('annonce l’absence de mouvement plutôt qu’un panneau vide', async () => {
    obtenirMetriques.mockResolvedValue(metriques({ recent_transactions: [] }))
    afficher()

    expect(await screen.findByText(/Aucune transaction/i)).toBeInTheDocument()
  })
})

describe('le mode confidentialité', () => {
  async function activer() {
    fireEvent.click(await screen.findByRole('button', { name: /Masquer/i }))
  }

  it('masque les montants d’un seul geste, panneau des transactions compris', async () => {
    // Les grandes cartes reçoivent `privacyMode` et masquent elles-mêmes ; le
    // panneau des transactions, lui, passe par la fonction `pc()` locale.
    // Vérifier les deux : c'est la promesse entière du bouton, et un montant
    // qui y échapperait se montrerait à quelqu'un qui se croit protégé.
    afficher()
    await screen.findByText(/Transactions récentes/i)
    const montantsAvant = Array.from(document.querySelectorAll('p')).map((n) => n.textContent ?? '')
    expect(montantsAvant.some((t) => t.startsWith('+') && t.includes('15'))).toBe(true)

    await activer()

    const montantsApres = Array.from(document.querySelectorAll('p')).map((n) => n.textContent ?? '')
    expect(montantsApres.some((t) => t.startsWith('+') && t.includes('15'))).toBe(false)
    expect(montantsApres.some((t) => t.includes('••••••'))).toBe(true)
    expect(screen.queryByText(/123\s*456/)).not.toBeInTheDocument()
  })

  it('retient le choix pour la prochaine visite', async () => {
    // Le masquage sert quand on travaille en public : le redemander à chaque
    // chargement le rendrait inutile.
    afficher()
    await screen.findByText(/Transactions récentes/i)

    await activer()

    expect(localStorage.getItem('investai-privacy')).toBe('true')
  })

  it('reprend l’état masqué au chargement suivant', async () => {
    localStorage.setItem('investai-privacy', 'true')
    afficher()

    await screen.findByText(/Transactions récentes/i)
    expect(screen.getAllByText('••••••').length).toBeGreaterThan(0)
  })

  it('se lève sur un second geste', async () => {
    localStorage.setItem('investai-privacy', 'true')
    afficher()
    await screen.findByText(/Transactions récentes/i)

    fireEvent.click(screen.getByRole('button', { name: /Afficher/i }))

    expect(screen.queryByText('••••••')).not.toBeInTheDocument()
    expect(localStorage.getItem('investai-privacy')).toBe('false')
  })
})

describe('les requêtes que la page déclenche', () => {
  it('ne charge les indices de référence qu’une fois demandés', async () => {
    // Ils sont lourds et ne servent qu'à une comparaison ponctuelle.
    afficher()
    await screen.findByText(/Transactions récentes/i)

    expect(obtenirBenchmarks).not.toHaveBeenCalled()
  })

  it('recharge les métriques quand la période change', async () => {
    afficher()
    await screen.findByText(/Transactions récentes/i)
    expect(obtenirMetriques).toHaveBeenCalledWith(0)

    fireEvent.click(screen.getByRole('button', { name: '24h' }))

    await waitFor(() => expect(obtenirMetriques).toHaveBeenCalledWith(1))
  })

  it('cesse de rafraîchir quand l’onglet passe à l’arrière-plan', async () => {
    // Sans cette garde, un onglet oublié interroge le serveur toutes les
    // minutes pour un écran que personne ne regarde. L'attente doit dépasser
    // largement tout intervalle plausible, sinon le test passerait aussi avec
    // un rafraîchissement actif.
    pageVisible.valeur = false
    afficher()
    await screen.findByText(/Transactions récentes/i)

    await new Promise((r) => setTimeout(r, 400))

    expect(obtenirMetriques).toHaveBeenCalledTimes(1)
  })
})
