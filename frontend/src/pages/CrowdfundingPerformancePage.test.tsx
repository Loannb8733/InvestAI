import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import CrowdfundingPerformancePage, {
  SERIES_GRAPHIQUE,
  LARGEUR_ITEM_LEGENDE,
} from './CrowdfundingPerformancePage'

// `vi.mock` est remonté au-dessus des déclarations du module : les données du
// projet fictif vivent donc dans la factory, pas à côté.
// `vi.mock` est remonté au-dessus des déclarations du module : les données du
// projet fictif vivent donc dans la factory, pas à côté.
//
// `getPerformance` renvoie `{ projects: [...] }`, et le graphique n'est rendu
// que pour les projets non terminés.
vi.mock('@/services/api', () => ({
  crowdfundingApi: {
    getPerformance: vi.fn().mockResolvedValue({
      projects: [
        {
          id: '1',
          project_name: 'BANDOL - 87 CAPELAN',
          platform: 'Test',
          status: 'active',
          invested: 1000,
          projected_interest_gross: 120,
          interest_earned: 40,
          annual_rate: 12,
          realized_xirr: 8,
          xirr_gap: -4,
          on_track: true,
          elapsed_months: 6,
          months: 12,
          progress_percent: 50,
          repayment_type: 'in_fine',
          tax_rate: 30,
        },
      ],
    }),
    getTaxReport: vi.fn().mockResolvedValue(null),
  },
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <CrowdfundingPerformancePage />
    </QueryClientProvider>
  )
}

/**
 * La légende du graphique reprenait les clés des séries. « Intérêts projetés
 * (bruts) » mesure 131 px pour les 70 alloués : les deux entrées se
 * chevauchaient de 61 px, mesurés à l'écran. Nivo ne renvoie pas à la ligne, et
 * élargir n'aurait fait que déplacer le problème sur un écran étroit.
 *
 * Nivo ne rend rien sous jsdom — `ResponsiveBar` attend une largeur que le DOM
 * simulé ne fournit pas. Ce qui se vérifie ici, c'est donc la source dont
 * dérivent les données, la légende et les couleurs : un libellé trop long y
 * serait refusé avant d'atteindre l'écran.
 */
describe('Graphique « Intérêts Projetés vs Perçus » — légende', () => {
  // Police de légende à 11 px : ~5,6 px par caractère, plus le symbole (10 px)
  // et son espacement. Approximation volontairement prudente.
  const largeurApprox = (texte: string) => texte.length * 5.6 + 16

  it('chaque libellé tient dans la largeur allouée', () => {
    for (const serie of SERIES_GRAPHIQUE) {
      expect(largeurApprox(serie.libelle), serie.libelle).toBeLessThanOrEqual(LARGEUR_ITEM_LEGENDE)
    }
  })

  it('les clés, elles, ne tiendraient pas — le tooltip les porte', () => {
    // C'est bien le défaut d'origine : afficher `cle` dans la légende déborde.
    const laPlusLongue = SERIES_GRAPHIQUE.reduce((a, b) => (a.cle.length >= b.cle.length ? a : b))
    expect(largeurApprox(laPlusLongue.cle)).toBeGreaterThan(LARGEUR_ITEM_LEGENDE)
  })

  it('distingue les deux séries sans libellés identiques', () => {
    const libelles = SERIES_GRAPHIQUE.map((s) => s.libelle)
    expect(new Set(libelles).size).toBe(libelles.length)
  })

  it('garde des clés explicites pour le tooltip', () => {
    for (const serie of SERIES_GRAPHIQUE) {
      expect(serie.cle).toMatch(/Intérêts/)
    }
  })
})

describe('CrowdfundingPerformancePage', () => {
  it('affiche le titre qui porte le sens du graphique', async () => {
    renderPage()
    expect(await screen.findByText('Intérêts Projetés vs Perçus par Projet')).toBeInTheDocument()
    expect(screen.getByText('montants bruts de fiscalité')).toBeInTheDocument()
  })
})
