import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import SimulationsPage from './SimulationsPage'

/**
 * Filet de caractérisation de `SimulationsPage` (2 399 lignes, dont 2 081 dans
 * une seule fonction — le plus gros fichier du projet).
 *
 * Ces tests épinglent le comportement **actuel**, verrues comprises. Ce ne sont
 * pas des tests de spécification : leur seul rôle est de faire échouer un
 * découpage qui changerait ce que la page fait aujourd'hui.
 *
 * Ce qu'ils visent en priorité, ce n'est pas le rendu — c'est la **traduction
 * des paramètres**. La page affiche des taux en pourcentages et des dépenses
 * mensuelles ; le backend attend des décimales et des dépenses annuelles. Trois
 * conversions et deux omissions vivent entre les deux, réparties dans un
 * `mutationFn` de 20 lignes au milieu de 2 000 autres. Un découpage qui
 * déplacerait ce bloc sans le comprendre enverrait `withdrawal_rate: 4` — soit
 * 400 % — sans que rien à l'écran ne le signale.
 */

const getMetricsMock = vi.hoisted(() => vi.fn())
const fireProbabilisticMock = vi.hoisted(() => vi.fn())
const listMock = vi.hoisted(() => vi.fn())
const simulateDCAMock = vi.hoisted(() => vi.fn())
const projectPortfolioMock = vi.hoisted(() => vi.fn())
const getMonteCarloMock = vi.hoisted(() => vi.fn())
const saveMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  dashboardApi: { getMetrics: getMetricsMock },
  simulationsApi: {
    fireProbabilistic: fireProbabilisticMock,
    projectPortfolio: projectPortfolioMock,
    simulateDCA: simulateDCAMock,
    list: listMock,
    save: saveMock,
    delete: vi.fn(),
  },
  analyticsApi: { getMonteCarlo: getMonteCarloMock },
}))

vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('@nivo/line', () => ({ ResponsiveLine: () => null }))
vi.mock('@/components/charts/nivo-theme', () => ({
  // `color` est une fonction, pas une chaîne : un double qui rend '#000'
  // laisse passer le rendu jusqu'à `color('--chart-1')`, qui lève.
  useNivoTheme: () => ({ color: () => '#000', palette: ['#000'], theme: {} }),
}))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ user: { preferredCurrency: 'EUR' } }),
}))

function resultatFire(surcharges: Record<string, unknown> = {}) {
  return {
    prob_by_year: [{ year: 1, prob: 0.1 }],
    prob_at_horizon: 0.42,
    fire_year_p10: null,
    fire_year_p50: 12,
    fire_year_p90: null,
    final_value_p10: 1,
    final_value_p50: 2,
    final_value_p90: 3,
    fire_number_today: 900000,
    survival_prob_30y: 0.9,
    median_path: [],
    n_paths: 500,
    currency: 'EUR',
    assumptions: {
      current_value: 50000,
      monthly_contribution: 500,
      annual_expenses: 36000,
      withdrawal_rate: 0.04,
      annual_return_mean: 0.07,
      annual_volatility: 0.15,
      inflation: 0.02,
      index_contributions: true,
      years_horizon: 30,
      n_paths: 500,
      defaults_from: null,
    },
    ...surcharges,
  }
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SimulationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  getMetricsMock.mockResolvedValue({ total_value: 50000 })
  listMock.mockResolvedValue([])
  fireProbabilisticMock.mockResolvedValue(resultatFire())
})

describe('SimulationsPage — rendu', () => {
  it('rend les quatre onglets, FIRE ouvert par défaut', async () => {
    afficher()

    expect(await screen.findByRole('tab', { name: /FIRE/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Projection/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Monte Carlo/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /DCA/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /FIRE/i })).toHaveAttribute('aria-selected', 'true')
  })

  it("le titre reste un h2 : le h1 de la page appartient au layout (UX-02)", async () => {
    afficher()

    const titre = await screen.findByText('Simulations', { selector: 'h2' })
    expect(titre.tagName).toBe('H2')
  })

  it("affiche la valeur du portefeuille rapportée par le dashboard", async () => {
    afficher()

    expect(await screen.findByText(/Portefeuille actuel/)).toBeInTheDocument()
  })

  it("un échec du chargement des scénarios n'emporte pas la page", async () => {
    listMock.mockRejectedValue(new Error('boom'))
    afficher()

    // La page reste utilisable : les onglets et le calculateur répondent encore.
    expect(await screen.findByRole('tab', { name: /FIRE/i })).toBeInTheDocument()
  })
})

describe('SimulationsPage — traduction des paramètres FIRE', () => {
  async function lancerFire() {
    afficher()
    // Attendre que le dashboard ait répondu : le pré-remplissage de la valeur
    // du portefeuille passe par un effet, et le test suivant épingle ce qui
    // est envoyé quand on clique avant.
    await screen.findByText(/Portefeuille actuel/)
    fireEvent.click(screen.getByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))
    await waitFor(() => expect(fireProbabilisticMock).toHaveBeenCalled())
    return fireProbabilisticMock.mock.calls[0][0]
  }

  it('convertit les taux affichés en pourcentages vers des décimales', async () => {
    const envoye = await lancerFire()

    // 4 % à l'écran, 0.04 sur le fil. Envoyer 4 demanderait au backend un
    // taux de retrait de 400 %.
    expect(envoye.withdrawal_rate).toBe(0.04)
    expect(envoye.inflation).toBe(0.02)
  })

  it('convertit les dépenses mensuelles en dépenses annuelles', async () => {
    const envoye = await lancerFire()

    expect(envoye.annual_expenses).toBe(36000)
    expect(envoye).not.toHaveProperty('monthly_expenses')
  })

  it('omet les champs laissés à null au lieu de les envoyer', async () => {
    const envoye = await lancerFire()

    // `undefined` et non `null` : le backend distingue « non fourni » — il
    // applique alors le profil investisseur — de « fourni à zéro ».
    expect(envoye.monthly_contribution).toBeUndefined()
    expect(envoye.annual_return_mean).toBeUndefined()
    expect(envoye.annual_volatility).toBeUndefined()
  })

  it('transmet la valeur du portefeuille pré-remplie depuis le dashboard', async () => {
    const envoye = await lancerFire()

    expect(envoye.current_value).toBe(50000)
  })

  it("omet la valeur du portefeuille si l'on calcule avant la réponse du dashboard", async () => {
    // Le pré-remplissage passe par un effet déclenché à l'arrivée des données.
    // Cliquer avant laisse le champ à 0 — et 0 est omis, pas envoyé : le
    // backend applique alors sa propre valeur plutôt qu'un portefeuille vide.
    getMetricsMock.mockReturnValue(new Promise(() => {}))
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))
    await waitFor(() => expect(fireProbabilisticMock).toHaveBeenCalled())

    expect(fireProbabilisticMock.mock.calls[0][0].current_value).toBeUndefined()
  })

  it("réinjecte dans les champs les hypothèses réellement appliquées", async () => {
    afficher()
    await screen.findByText(/Portefeuille actuel/)
    fireEvent.click(screen.getByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))

    // Le backend renvoie 0.07 ; le champ doit afficher 7 (et non 0.07).
    await waitFor(() => {
      expect(screen.getByLabelText(/Rendement annuel/i)).toHaveValue(7)
    })
  })

  it("signale les hypothèses que le backend a tirées du profil investisseur", async () => {
    fireProbabilisticMock.mockResolvedValue(
      resultatFire({
        assumptions: {
          ...resultatFire().assumptions,
          defaults_from: { annual_return_mean: 'profil investisseur' },
        },
      }),
    )
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))

    expect(await screen.findByText(/Pré-rempli depuis votre profil investisseur/i)).toBeInTheDocument()
  })
})

describe('SimulationsPage — les trois autres onglets', () => {
  async function ouvrirOnglet(nom: RegExp) {
    afficher()
    await screen.findByText(/Portefeuille actuel/)
    // `mouseDown`, pas `click` : Radix active un onglet au pointer-down. Un
    // clic seul laisse `aria-selected` à false et le panneau ne se monte pas.
    // (`@testing-library/user-event`, qui émet la séquence complète, n'est pas
    // installé dans ce projet.)
    fireEvent.mouseDown(screen.getByRole('tab', { name: nom }))
  }

  /**
   * Trois onglets, trois conventions d'unité — et c'est le backend qui les
   * impose, pas un oubli du front.
   *
   * FIRE convertit les pourcentages en décimales avant l'envoi ; Projection et
   * DCA envoient le pourcentage tel quel, leurs endpoints le validant en
   * `ge=-20, le=50` et divisant eux-mêmes par 100.
   *
   * Ces deux tests existent pour un découpage précis : celui qui, voyant trois
   * onglets voisins traiter les taux différemment, « harmoniserait » sur le cas
   * FIRE. Il diviserait alors par 100 des taux déjà attendus en pourcentages —
   * une projection à 7 % deviendrait 0,07 %, et rien à l'écran ne le dirait.
   */
  it('Projection envoie les taux en pourcentages, sans conversion', async () => {
    projectPortfolioMock.mockResolvedValue({
      projections: [], final_value: 0, total_contributions: 0, total_returns: 0, real_final_value: 0,
    })
    await ouvrirOnglet(/Projection/i)

    fireEvent.click(screen.getByRole('button', { name: /^Projeter$/i }))
    await waitFor(() => expect(projectPortfolioMock).toHaveBeenCalled())

    const envoye = projectPortfolioMock.mock.calls[0][0]
    expect(envoye.expected_return).toBe(7)
    expect(envoye.inflation_rate).toBe(2)
  })

  it('DCA envoie lui aussi les taux en pourcentages', async () => {
    simulateDCAMock.mockResolvedValue({
      total_invested: 0, final_value: 0, average_cost: 0, total_units: 0, return_percent: 0,
      dca_p10: 0, dca_p50: 0, dca_p90: 0, lumpsum_p10: 0, lumpsum_p50: 0, lumpsum_p90: 0,
      prob_dca_beats_ls: 0, n_paths: 500, projections: [],
    })
    await ouvrirOnglet(/DCA/i)

    fireEvent.click(screen.getByRole('button', { name: /Simuler \(500 trajectoires\)/i }))
    await waitFor(() => expect(simulateDCAMock).toHaveBeenCalled())

    const envoye = simulateDCAMock.mock.calls[0][0]
    expect(envoye.expected_return).toBe(7)
    expect(envoye.expected_volatility).toBe(20)
  })

  it('Monte Carlo passe ses paramètres en arguments positionnels', async () => {
    getMonteCarloMock.mockResolvedValue({ percentiles: {}, expected_return: 0, prob_positive: 0 })
    await ouvrirOnglet(/Monte Carlo/i)

    fireEvent.click(screen.getByRole('button', { name: /Simuler \(5 000 chemins\)/i }))
    await waitFor(() => expect(getMonteCarloMock).toHaveBeenCalled())

    // `getMonteCarlo(horizon, _, retrait, ter, retraitMensuel)` : les zéros
    // deviennent `undefined` via `|| undefined`, ce qui laisse le backend
    // appliquer ses défauts plutôt que de forcer un retrait nul.
    const [horizon, second, retrait, ter] = getMonteCarloMock.mock.calls[0]
    expect(horizon).toBe(365)
    expect(second).toBeUndefined()
    expect(retrait).toBeUndefined()
    expect(ter).toBe(0.25)
  })
})

describe('SimulationsPage — sauvegarde de scénario', () => {
  /**
   * `buildScenarioPayload` refait, pour la sauvegarde, les conversions que la
   * mutation FIRE fait pour l'affichage — le même `* 10000 / 100` apparaît deux
   * fois dans le fichier, à 120 lignes d'écart.
   *
   * Un découpage qui n'emporterait qu'un des deux sites laisserait le scénario
   * enregistré avec des taux en décimales, relus plus tard comme des
   * pourcentages : un rendement de 7 % archivé, puis réaffiché à 0,07 %.
   */
  it("enregistre les hypothèses appliquées, taux reconvertis en pourcentages", async () => {
    saveMock.mockResolvedValue({ id: 's1' })
    afficher()
    await screen.findByText(/Portefeuille actuel/)

    fireEvent.click(screen.getByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))
    await waitFor(() => expect(fireProbabilisticMock).toHaveBeenCalled())

    fireEvent.click(await screen.findByRole('button', { name: /Sauvegarder ce scénario/i }))
    fireEvent.change(await screen.findByLabelText(/Nom du scénario/i), {
      target: { value: 'Retraite à 45 ans' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Enregistrer$/i }))

    await waitFor(() => expect(saveMock).toHaveBeenCalled())
    const { inputs } = saveMock.mock.calls[0][0].parameters

    // Le backend a renvoyé 0.07 et 0.04 ; le scénario archive 7 et 4.
    expect(inputs.expected_annual_return).toBe(7)
    expect(inputs.withdrawal_rate).toBe(4)
    expect(inputs.annual_volatility).toBe(15)
  })

  it("refuse d'enregistrer un scénario sans nom", async () => {
    afficher()
    await screen.findByText(/Portefeuille actuel/)

    fireEvent.click(screen.getByRole('button', { name: /Simuler \(1 000 trajectoires\)/i }))
    await waitFor(() => expect(fireProbabilisticMock).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: /Sauvegarder ce scénario/i }))

    expect(await screen.findByRole('button', { name: /^Enregistrer$/i })).toBeDisabled()
  })
})
