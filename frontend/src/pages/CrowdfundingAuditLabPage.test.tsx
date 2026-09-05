import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import CrowdfundingAuditLabPage from './CrowdfundingAuditLabPage'

vi.mock('@/services/api', () => ({
  crowdfundingApi: {
    listAudits: vi.fn().mockResolvedValue([]),
    getDashboard: vi.fn().mockResolvedValue({ projects: [] }),
    analyzeDocuments: vi.fn(),
  },
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CrowdfundingAuditLabPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

/**
 * UX-11 : l'Audit Lab est une route à part quand le reste du Crowdfunding est
 * en onglets. La route reste justifiée — les onglets montrent ce qu'on possède,
 * l'Audit Lab évalue un projet qu'on ne possède pas encore — mais la page ne
 * disait pas d'où l'on venait et ne ramenait nulle part.
 */
describe("CrowdfundingAuditLabPage — repère de navigation", () => {
  it("porte un fil d'Ariane", () => {
    renderPage()
    expect(screen.getByRole('navigation', { name: /fil d'ariane/i })).toBeInTheDocument()
  })

  it('ramène au Crowdfunding par un lien', () => {
    renderPage()
    const lien = screen.getByRole('link', { name: 'Crowdfunding' })
    expect(lien).toHaveAttribute('href', '/crowdfunding')
  })

  it('situe la page courante dans le fil', () => {
    renderPage()
    const fil = screen.getByRole('navigation', { name: /fil d'ariane/i })
    expect(fil).toHaveTextContent('Audit Lab')
  })

  it('garde un seul titre de niveau 1', () => {
    renderPage()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })
})
