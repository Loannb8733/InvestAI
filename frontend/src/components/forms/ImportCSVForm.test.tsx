import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImportCSVForm from './ImportCSVForm'

/**
 * Ce que l'utilisateur lit après un import CSV.
 *
 * Le fichier peut se solder de trois façons — des lignes importées, des lignes
 * en erreur, et des lignes **déjà présentes**. Seules les deux premières
 * étaient dites. Un fichier entièrement déjà connu revenait en
 * `0 succès, 0 erreur`, que ce composant rendait en « Échec de l'import —
 * 0 erreurs détectées » : un échec annoncé, aucune erreur à montrer, aucune
 * piste (NEW-60).
 *
 * Le backend compte désormais ces lignes et les renvoie ; ces tests vérifient
 * que le message les reflète, y compris quand la réponse ne les porte pas —
 * une réponse d'avant le correctif ne doit pas casser l'affichage.
 */

const importerCSV = vi.hoisted(() => vi.fn())
const listePlateformes = vi.hoisted(() => vi.fn())
const listePortefeuilles = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  transactionsApi: { importCSV: importerCSV, getCSVPlatforms: listePlateformes },
  portfoliosApi: { list: listePortefeuilles },
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/lib/invalidate-queries', () => ({ invalidateAllFinancialData: vi.fn() }))

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ImportCSVForm open onOpenChange={() => {}} portfolioId="p1" />
    </QueryClientProvider>,
  )
}

/** Dépose un fichier dans le champ et déclenche l'import. */
async function importer() {
  const champ = document.querySelector('input[type="file"]') as HTMLInputElement
  const fichier = new File(['symbol,type,quantity,price\n'], 'historique.csv', { type: 'text/csv' })
  fireEvent.change(champ, { target: { files: [fichier] } })
  // Plusieurs boutons portent « Importer » (l'ouverture de la boîte, le titre) :
  // celui-ci est le seul qui nomme le portefeuille de destination.
  const bouton = await screen.findByRole('button', { name: /Importer dans/i })
  fireEvent.click(bouton)
}

beforeEach(() => {
  vi.clearAllMocks()
  // TanStack Query refuse une réponse `undefined` : les doubles rendent des
  // valeurs plausibles, sinon chaque test traîne deux avertissements.
  listePortefeuilles.mockResolvedValue([{ id: 'p1', name: 'Principal' }])
  listePlateformes.mockResolvedValue({ platforms: ['Crypto.com', 'Binance', 'Kraken'] })
})

describe("le compte rendu d'import", () => {
  it('annonce un fichier entièrement déjà connu sans parler d’échec', async () => {
    importerCSV.mockResolvedValue({
      success_count: 0,
      error_count: 0,
      skipped_count: 12,
      errors: [],
      created_transactions: [],
    })
    afficher()

    await importer()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.title).toBe('Rien de nouveau')
    expect(message.description).toContain('12')
    expect(message.variant).toBeUndefined()
  })

  it('mentionne les lignes ignorées à côté des lignes importées', async () => {
    importerCSV.mockResolvedValue({
      success_count: 3,
      error_count: 0,
      skipped_count: 5,
      errors: [],
      created_transactions: ['t1', 't2', 't3'],
    })
    afficher()

    await importer()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.title).toBe('Import réussi')
    expect(message.description).toContain('3 transactions importées')
    expect(message.description).toContain('5 déjà présentes')
  })

  it('garde le message d’échec quand il y a de vraies erreurs', async () => {
    importerCSV.mockResolvedValue({
      success_count: 0,
      error_count: 4,
      skipped_count: 0,
      errors: ['Unknown transaction type: donation'],
      created_transactions: [],
    })
    afficher()

    await importer()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.variant).toBe('destructive')
    expect(message.description).toContain('4 erreurs')
  })

  it('supporte une réponse sans le champ, comme avant le correctif', async () => {
    // Le champ est facultatif côté type. Ce qui protège à l'exécution n'est pas
    // le `?? 0` — cosmétique, `undefined > 0` vaut déjà `false` — mais la
    // comparaison elle-même : sans elle, le message afficherait
    // « undefined déjà présentes ».
    importerCSV.mockResolvedValue({
      success_count: 2,
      error_count: 0,
      errors: [],
      created_transactions: ['t1', 't2'],
    })
    afficher()

    await importer()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.title).toBe('Import réussi')
    expect(message.description).not.toContain('undefined')
    expect(message.description).not.toContain('ignorées')
  })

  it('affiche le décompte des lignes ignorées dans le récapitulatif', async () => {
    importerCSV.mockResolvedValue({
      success_count: 1,
      error_count: 0,
      skipped_count: 7,
      errors: [],
      created_transactions: ['t1'],
    })
    afficher()

    await importer()

    expect(await screen.findByText(/7 déjà présentes/)).toBeInTheDocument()
    expect(screen.getByText(/1 importées/)).toBeInTheDocument()
  })
})
