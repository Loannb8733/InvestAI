import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ReportsPage from './ReportsPage'

/**
 * UX-04 — la panne d'une requête accessoire ne doit pas coûter la page.
 *
 * `getAvailableYears` ne sert qu'à peupler le sélecteur d'année fiscale, et le
 * code retombe sur l'année courante quand elle manque : tous les rapports
 * restent générables. Rendre ici un état d'erreur de page — comme sur les
 * écrans dont la requête porte le contenu — masquerait toute la page des
 * rapports pour une liste d'années indisponible. Ce serait une régression
 * déguisée en correctif.
 *
 * Ces tests verrouillent donc les deux faces : le signalement existe, et il
 * reste discret.
 */

const getAvailableYearsMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ years: [2024, 2025, 2026] })
)

vi.mock('@/services/api', () => ({
  reportsApi: {
    getAvailableYears: getAvailableYearsMock,
    downloadTaxPdf: vi.fn(),
    downloadTaxExcel: vi.fn(),
    downloadPortfolioPdf: vi.fn(),
    downloadTransactionsExcel: vi.fn(),
    downloadStockTaxExcel: vi.fn(),
  },
}))

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

// Les onglets lourds ne participent pas à ce qu'on vérifie ici.
vi.mock('@/components/reports/RebalancingTab', () => ({ default: () => null }))
vi.mock('@/components/reports/TaxSummaryPanel', () => ({ default: () => null }))
vi.mock('@/components/reports/OptimizationsTab', () => ({ default: () => null }))

function renderWithProviders() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      {/* Le sélecteur d'année vit dans l'onglet « fiscal », pas dans l'onglet
          par défaut : la page lit ?tab= pour choisir l'onglet initial. */}
      <MemoryRouter initialEntries={['/reports?tab=fiscal']}>
        <ReportsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ReportsPage — liste des années indisponible (UX-04)', () => {
  beforeEach(() => {
    getAvailableYearsMock.mockReset()
  })

  afterEach(() => {
    getAvailableYearsMock.mockResolvedValue({ years: [2024, 2025, 2026] })
  })

  it('signale que seule l\'année courante est proposée', async () => {
    getAvailableYearsMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    expect(await screen.findAllByText(/seule l'année courante est proposée/i)).not.toHaveLength(0)
  })

  it('propose de réessayer', async () => {
    getAvailableYearsMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    expect(await screen.findAllByRole('button', { name: /réessayer/i })).not.toHaveLength(0)
  })

  it('garde la page fonctionnelle : les rapports restent proposés', async () => {
    getAvailableYearsMock.mockRejectedValue(new Error('500'))
    renderWithProviders()
    await screen.findAllByText(/seule l'année courante est proposée/i)

    // Le point de tout le ticket : la page ne doit pas être remplacée par une
    // erreur. Si ces titres disparaissent, le « correctif » a cassé l'écran.
    expect(screen.getByText('Rapports')).toBeInTheDocument()
    expect(screen.queryByText('Impossible de charger ces données')).not.toBeInTheDocument()
  })

  it('ne signale rien quand le chargement réussit', async () => {
    getAvailableYearsMock.mockResolvedValue({ years: [2024, 2025] })
    renderWithProviders()
    await screen.findByText('Rapports')
    expect(screen.queryByText(/seule l'année courante est proposée/i)).not.toBeInTheDocument()
  })
})
