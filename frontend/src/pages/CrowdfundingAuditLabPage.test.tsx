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
 * l'Audit Lab évalue un projet qu'on ne possède pas encore.
 *
 * Le repère de navigation a d'abord été ajouté dans la page, puis remonté au
 * Header avec le fil d'Ariane global (UX-10). C'est `filParDefaut` qui garantit
 * désormais « Crowdfunding › Audit Lab » — voir `fil-ariane.test.tsx`. Ce qui
 * se vérifie ici, c'est que la page n'en rend plus un second.
 */
describe('CrowdfundingAuditLabPage', () => {
  it("ne rend pas son propre fil d'Ariane", () => {
    renderPage()
    expect(screen.queryByRole('navigation', { name: /fil d'ariane/i })).toBeNull()
  })

  it('garde un seul titre de niveau 1', () => {
    renderPage()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('annonce sa raison d\'être', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Audit Lab')
  })
})
