import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AddTransactionForm from './AddTransactionForm'

/**
 * Le formulaire par lequel les transactions entrent.
 *
 * `components/forms` était couvert à **0 %**. C'est pourtant ici que les
 * chiffres arrivent dans le système : une quantité, un prix, des frais. Deux
 * calculs y vivent, et tous deux se voient à l'écran :
 *
 * - la **saisie bidirectionnelle** — taper un total recalcule la quantité par
 *   `(total − frais) / prix` ;
 * - l'**aperçu de position** — ce que deviendra la quantité détenue selon le
 *   type de mouvement.
 *
 * Ces tests montent le formulaire pour de vrai et l'utilisent comme le ferait
 * l'utilisateur. Les appels réseau et les cours en direct sont doublés ; le
 * reste — validation Zod, react-hook-form, rendu — est parcouru.
 */

const listeActifs = vi.hoisted(() => vi.fn())
const listePortefeuilles = vi.hoisted(() => vi.fn())
const creerTransaction = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  assetsApi: { list: listeActifs, create: vi.fn() },
  portfoliosApi: { list: listePortefeuilles },
  transactionsApi: { create: creerTransaction },
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/hooks/useRealtimePrices', () => ({
  useRealtimePrices: () => ({ prices: { BTC: { price: 45000 } } }),
}))
vi.mock('@/lib/invalidate-queries', () => ({ invalidateAllFinancialData: vi.fn() }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selecteur: (e: unknown) => unknown) =>
    selecteur({ user: { preferredCurrency: 'EUR' } }),
}))

const ACTIF = {
  id: 'a1',
  symbol: 'BTC',
  name: 'Bitcoin',
  portfolio_id: 'p1',
  exchange: 'Binance',
  quantity: 2,
  asset_type: 'crypto',
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AddTransactionForm open onOpenChange={() => {}} assetId="a1" assetSymbol="BTC" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  listeActifs.mockResolvedValue([ACTIF])
  listePortefeuilles.mockResolvedValue([{ id: 'p1', name: 'Principal' }])
  creerTransaction.mockResolvedValue({ id: 't1' })
})

async function champ(nom: RegExp) {
  return (await screen.findByLabelText(nom)) as HTMLInputElement
}

/** Le bouton d'envoi porte le libellé du type choisi — « Achat » comme le
 *  sélecteur de type juste au-dessus. C'est `type="submit"` qui les sépare. */
function boutonEnvoyer(): HTMLButtonElement {
  const bouton = document.querySelector('button[type="submit"]')
  if (!bouton) throw new Error("bouton d'envoi introuvable")
  return bouton as HTMLButtonElement
}

describe('rendu', () => {
  it('propose les types de mouvement', async () => {
    afficher()

    // Deux boutons portent « Achat » : le sélecteur de type et le bouton
    // d'envoi, qui reprend le libellé du type choisi.
    expect((await screen.findAllByRole('button', { name: /^Achat$/i })).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /^Vente$/i })).toBeInTheDocument()
  })

  it("ouvre sur un achat, et le bouton d'envoi le reprend", async () => {
    afficher()

    await screen.findByLabelText(/Quantité/i)

    expect(boutonEnvoyer().textContent).toMatch(/Achat/)
  })

  it('changer de type change le bouton d\'envoi', async () => {
    // Le libellé de l'envoi suit le type : on ne confond pas un achat et une
    // vente au moment de valider.
    afficher()

    fireEvent.click(await screen.findByRole('button', { name: /^Vente$/i }))

    await waitFor(() => expect(boutonEnvoyer().textContent).toMatch(/Vente/))
  })
})

describe('saisie bidirectionnelle', () => {
  it('déduit la quantité du total saisi, frais déduits', async () => {
    /* 1 000 EUR au prix de 40 000, moins 20 EUR de frais, donnent
       0,0245 BTC — et non 0,025. Oublier les frais surévaluerait la quantité
       acquise, donc minorerait le prix de revient. */
    afficher()

    fireEvent.change(await champ(/Prix unitaire/i), { target: { value: '40000' } })
    fireEvent.change(await champ(/Frais/i), { target: { value: '20' } })
    fireEvent.change(await champ(/Total/i), { target: { value: '1000' } })

    await waitFor(async () => {
      expect((await champ(/Quantité/i)).value).toBe('0.0245')
    })
  })

  it('ne déduit rien tant que le prix est nul', async () => {
    // Diviser par zéro donnerait `Infinity` dans le champ quantité.
    afficher()

    fireEvent.change(await champ(/Total/i), { target: { value: '1000' } })

    const quantite = await champ(/Quantité/i)
    expect(quantite.value === '' || Number(quantite.value) === 0).toBe(true)
  })

  it('ne rend jamais une quantité négative', async () => {
    // Des frais supérieurs au total : le résultat est borné à zéro plutôt que
    // de proposer d'acheter une quantité négative.
    afficher()

    fireEvent.change(await champ(/Prix unitaire/i), { target: { value: '40000' } })
    fireEvent.change(await champ(/Frais/i), { target: { value: '500' } })
    fireEvent.change(await champ(/Total/i), { target: { value: '100' } })

    await waitFor(async () => {
      expect(Number((await champ(/Quantité/i)).value)).toBe(0)
    })
  })
})

describe('envoi', () => {
  it('refuse une quantité nulle, et le dit', async () => {
    /** Le schéma exige une quantité strictement positive.

    L'assertion porte sur le **message affiché**, pas sur l'absence d'appel :
    une absence peut être vraie pour une tout autre raison — c'est ce qu'a
    montré le canari, qui relâchait la validation sans faire tomber le test. */
    afficher()

    fireEvent.change(await champ(/Quantité/i), { target: { value: '0' } })
    fireEvent.change(await champ(/Prix unitaire/i), { target: { value: '40000' } })
    fireEvent.click(boutonEnvoyer())

    expect(await screen.findByText(/Quantité doit être positive/i)).toBeInTheDocument()
    expect(creerTransaction).not.toHaveBeenCalled()
  })

  it('accepte un prix nul', async () => {
    // Un airdrop ou une récompense de staking arrive sans contrepartie : le
    // prix zéro est légitime, contrairement à la quantité.
    afficher()

    fireEvent.change(await champ(/Quantité/i), { target: { value: '1' } })
    fireEvent.change(await champ(/Prix unitaire/i), { target: { value: '0' } })
    await screen.findByLabelText(/Quantité/i)
    fireEvent.click(boutonEnvoyer())

    await waitFor(() => expect(creerTransaction).toHaveBeenCalled())
  })
})
