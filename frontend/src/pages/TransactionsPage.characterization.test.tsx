import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { listTransactions, TRANSACTIONS, transactionRoutes } from '@/test/transactionFixtures'
import { chooseOption, reduceMotion, renderWithQuery, settle } from '@/test/render'
import TransactionsPage from './TransactionsPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const listCalls = () => calls.filter((c) => c.url === '/transactions')
const rows = () => [...document.querySelectorAll('tbody tr')].map((tr) => visibleText(tr).join(' '))
const combobox = (index: number) => screen.getAllByRole('combobox')[index]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/transactions/${name}.json`)
}

async function open() {
  renderWithQuery(<TransactionsPage />)
  await screen.findByText('Historique')
  await pause(50)
}

async function filterBy(index: number, option: string) {
  const before = listCalls().length
  chooseOption(combobox(index), option)
  await settle(() => listCalls().length > before)
  await pause(50)
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(transactionRoutes())
  toasts.length = 0
  reduceMotion()
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Transactions — liste', () => {
  it('affiche les statistiques et la première page', async () => {
    await open()
    await golden('liste', { calls, toasts, text: visibleText() })
  })

  it('passe à la page suivante', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Page suivante' }))
    await pause(20)
    await golden('page_suivante', { rows: rows(), pagination: visibleText(screen.getByRole('button', { name: 'Page 1' }).closest('.border-t') as HTMLElement) })
  })

  it('trie par quantité, puis dans l’autre sens', async () => {
    await open()
    fireEvent.click(screen.getByText('Quantité', { selector: 'th div' }))
    await pause(20)
    const descending = rows().slice(0, 5)
    fireEvent.click(screen.getByText('Quantité', { selector: 'th div' }))
    await pause(20)
    await golden('tri_quantite', { descending, ascending: rows().slice(0, 5) })
  })

  it('charge la suite au-delà de deux cents lignes', async () => {
    const extra = { ...TRANSACTIONS[16], id: 'old1', executed_at: '2024-12-01T09:00:00Z', created_at: '2024-12-01T09:00:00Z' }
    routes['GET /transactions'] = (config) => {
      const params = config.params as { skip: number }
      if (params.skip === 200) return ok({ items: [extra], total: TRANSACTIONS.length + 1 })(config)
      return listTransactions(TRANSACTIONS, 1)(config)
    }
    await open()
    const before = visibleText()
    fireEvent.click(screen.getByRole('button', { name: 'Charger plus de transactions' }))
    await settle(() => listCalls().length > 1)
    await pause(50)
    await golden('charger_plus', { before, calls: listCalls(), text: visibleText() })
  })
})

describe('Transactions — filtres', () => {
  it('filtre par type', async () => {
    await open()
    await filterBy(2, 'Ventes')
    await golden('filtre_type', { calls: listCalls(), text: visibleText() })
  })

  it('filtre par portefeuille', async () => {
    await open()
    await filterBy(0, 'Bourse')
    await golden('filtre_portefeuille', { calls: listCalls(), text: visibleText() })
  })

  it('filtre par plateforme sans nom', async () => {
    await open()
    await filterBy(4, 'Manuel (2)')
    await golden('filtre_manuel', { calls: listCalls(), rows: rows() })
  })

  it('recherche après une pause de saisie', async () => {
    await open()
    fireEvent.change(screen.getByPlaceholderText('Rechercher...'), { target: { value: 'e' } })
    fireEvent.change(screen.getByPlaceholderText('Rechercher...'), { target: { value: 'eth' } })
    await settle(() => listCalls().length > 1)
    await pause(400)
    await golden('recherche', { calls: listCalls(), rows: rows() })
  })

  it('efface les filtres', async () => {
    await open()
    await filterBy(2, 'Ventes')
    fireEvent.click(screen.getByRole('button', { name: /Effacer \(1\)/ }))
    await settle(() => rows().length === 20)
    await pause(50)
    await golden('filtres_effaces', { calls: listCalls(), rows: rows().length })
  })

  it('n’affiche rien quand aucun mouvement ne correspond', async () => {
    await open()
    await filterBy(2, 'Dividendes')
    const card = screen.getByText('Aucun résultat').closest('.rounded-lg') ?? document.body
    await golden('filtre_vide', { text: visibleText(card as HTMLElement), page: visibleText() })
  })
})

describe('Transactions — états', () => {
  it('propose d’ajouter une première transaction', async () => {
    routes['GET /transactions'] = ok({ items: [], total: 0 })
    await open()
    await golden('aucune_transaction', { calls, text: visibleText() })
  })

  it('réagit à une liste indisponible', async () => {
    routes['GET /transactions'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<TransactionsPage />)
    await screen.findByText('Impossible de charger les transactions')
    await pause(50)
    await golden('liste_erreur', { calls, toasts, text: visibleText() })
  })

  it('montre les montants en dollars à part', async () => {
    await open()
    const cards = screen.getByText(/Total achats/).closest('.grid') as HTMLElement
    await golden('devises', { cards: visibleText(within(cards).getByText(/Total achats/).closest('.spot-card') as HTMLElement) })
  })
})
