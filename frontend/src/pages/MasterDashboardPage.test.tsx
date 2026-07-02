import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MasterDashboardPage from './MasterDashboardPage'

// The net-worth query fails; the crowdfunding queries resolve empty so only the
// metrics error path is under test.
vi.mock('@/services/api', () => ({
  dashboardApi: { getMetrics: vi.fn().mockRejectedValue(new Error('network down')) },
  crowdfundingApi: {
    getDashboard: vi.fn().mockResolvedValue({ total_invested: 0 }),
    listAudits: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { preferredCurrency: 'EUR' } }),
}))

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MasterDashboardPage />
    </QueryClientProvider>,
  )
}

describe('MasterDashboardPage — metrics error state', () => {
  it('shows an explicit error + retry instead of a silent €0 net worth', async () => {
    renderPage()

    // The trust-critical assertion: an error surface appears, not a €0 dashboard.
    expect(
      await screen.findByText(/Impossible de charger votre patrimoine/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Réessayer/i })).toBeInTheDocument()
  })
})
