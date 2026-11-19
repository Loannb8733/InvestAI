import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { formatCurrency } from '@/lib/utils'
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
vi.mock('@/hooks/useRealtimePrices', () => ({ useRealtimePrices: () => ({ prices: {} }) }))

const server = createFakeServer()
const { calls, routes } = server
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const failure = () => ({ status: 500, data: { detail: 'boom' } })
const writes = () => calls.filter((c) => c.method !== 'GET')
const listReads = () => calls.filter((c) => c.method === 'GET' && c.url === '/transactions').length
const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })
const rowMenu = (index: number) => screen.getAllByRole('button', { name: 'Actions sur la transaction' })[index]
const only = (id: string) => listTransactions(TRANSACTIONS.filter((t) => t.id === id))
const listDetail = [{ type: 'enum', loc: ['body', 'asset_type'], msg: 'Input should be crypto, stock, etf' }]

async function open() {
  renderWithQuery(<TransactionsPage />)
  await screen.findByText('Historique')
  await pause(50)
}

async function menuItem(trigger: HTMLElement, name: RegExp) {
  fireEvent.keyDown(trigger, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name }))
}

async function openEdit(row: number) {
  await open()
  await menuItem(rowMenu(row), /Modifier/)
  return screen.findByRole('dialog')
}

async function openDialog(button: RegExp) {
  await open()
  fireEvent.click(screen.getByRole('button', { name: button }))
  return screen.findByRole('dialog')
}

async function fillPurchase(dialog: HTMLElement) {
  chooseOption(within(dialog).getByRole('combobox', { name: 'Portefeuille' }), 'Crypto')
  chooseOption(await within(dialog).findByRole('combobox', { name: 'Actif' }), 'BTC (Binance) - Bitcoin')
  type('quantity', '0.02')
  type('price', '50000')
  type('fee', '2')
  await pause(20)
}

async function openImport() {
  const dialog = await openDialog(/Importer/)
  const file = new File(['symbol;type\n'], 'binance.csv', { type: 'text/csv' })
  fireEvent.change(dialog.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } })
  chooseOption(within(dialog).getAllByRole('combobox')[0], 'Crypto')
  return dialog
}

async function filterSales() {
  chooseOption(screen.getAllByRole('combobox')[2], 'Ventes')
  await screen.findByText('Total ventes (filtrés)')
  await pause(50)
}

function optionsOf(combobox: HTMLElement) {
  fireEvent.keyDown(combobox, { key: 'Enter' })
  return screen.getAllByRole('option').map((option) => option.textContent)
}

async function settled() {
  await settle(() => toasts.length > 0)
  await pause(100)
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(transactionRoutes())
  toasts.length = 0
  reduceMotion()
  vi.spyOn(window.URL, 'createObjectURL').mockImplementation(() => 'blob:faux')
  vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  process.env.TZ = 'UTC'
  vi.restoreAllMocks()
})

describe('transactions — défauts corrigés', () => {
  it('n’envoie rien quand la modification ne change rien', async () => {
    const dialog = await openEdit(18)
    calls.length = 0
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    await settled()
    expect(writes()).toEqual([])
    expect(toasts.map((t) => t.title)).toEqual(['Aucune modification'])
  })

  it('garde le jour local d’un mouvement tardif et renvoie l’heure saisie', async () => {
    process.env.TZ = 'Europe/Paris'
    routes['GET /transactions'] = listTransactions([{ ...TRANSACTIONS[16], executed_at: '2025-03-10T23:30:00Z' }])
    const dialog = await openEdit(0)
    const date = dialog.querySelector('input[type="date"]') as HTMLInputElement
    const time = dialog.querySelector('input[type="time"]') as HTMLInputElement
    expect([date.value, time.value]).toEqual(['2025-03-11', '00:30'])
    fireEvent.change(time, { target: { value: '01:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    await settled()
    expect(writes().map((c) => c.body)).toEqual([{ executed_at: '2025-03-11T00:00:00.000Z' }])
  })

  it('affiche le montant total dans la devise de la transaction', async () => {
    routes['GET /transactions'] = only('t6')
    const dialog = await openEdit(0)
    expect(dialog.textContent).toContain(formatCurrency(526.75, 'USD'))
  })

  it('ne propose pas de tout supprimer sous un filtre et compte toutes les transactions', async () => {
    routes['GET /transactions'] = listTransactions(TRANSACTIONS, 250)
    await open()
    expect(screen.getByText(/et remet les quantités à zéro/).textContent).toContain('Supprime 273 transactions')
    await filterSales()
    expect(screen.queryByRole('button', { name: 'Tout supprimer' })).toBeNull()
  })

  it('n’avertit plus que les filtres ne couvrent que les lignes chargées', async () => {
    routes['GET /transactions'] = listTransactions(TRANSACTIONS, 250)
    await open()
    await filterSales()
    expect(screen.queryByText(/n'ont pas été parcourues/)).toBeNull()
  })

  it.each([
    ['une suppression', async () => {
      routes['DELETE /transactions/t2'] = failure
      await open()
      await menuItem(rowMenu(3), /Supprimer/)
      fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Supprimer' }))
    }],
    ['une modification', async () => {
      routes['PATCH /transactions/t1'] = failure
      const dialog = await openEdit(18)
      fireEvent.change(dialog.querySelectorAll('input')[2], { target: { value: '2.5' } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    }],
    ['un export', async () => {
      routes['GET /transactions/export-csv'] = failure
      await open()
      await menuItem(screen.getByRole('button', { name: 'Exporter' }), /Tout exporter/)
    }],
    ['un ajout', async () => {
      routes['POST /transactions'] = failure
      const dialog = await openDialog(/Nouvelle/)
      await fillPurchase(dialog)
      fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    }],
    ['un import', async () => {
      routes['POST /transactions/import-csv'] = () => ({ status: 400, data: { detail: 'Format de fichier non reconnu' } })
      const dialog = await openImport()
      fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    }],
  ])('signale l’échec d’%s par une seule notification', async (_, act) => {
    await act()
    await settled()
    expect(toasts).toHaveLength(1)
  })

  it('ne notifie pas une liste indisponible, déjà signalée dans la page', async () => {
    routes['GET /transactions'] = failure
    renderWithQuery(<TransactionsPage />)
    await screen.findByText('Impossible de charger les transactions')
    await pause(100)
    expect(toasts).toEqual([])
  })

  it('ne propose plus le type Fiat et rend lisible un refus dont le détail est une liste', async () => {
    routes['POST /assets'] = () => ({ status: 422, data: { detail: listDetail } })
    const dialog = await openDialog(/Nouvelle/)
    chooseOption(within(dialog).getByRole('combobox', { name: 'Portefeuille' }), 'Crypto')
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Nouveau' }))
    expect(optionsOf(within(dialog).getByRole('combobox', { name: "Type d'actif" }))).not.toContain('Fiat')
    fireEvent.keyDown(screen.getAllByRole('option')[0], { key: 'Enter' })
    fireEvent.change(within(dialog).getByPlaceholderText('BTC, AAPL...'), { target: { value: 'link' } })
    fireEvent.click(within(dialog).getByRole('combobox', { name: 'Plateforme...' }))
    fireEvent.click(await screen.findByRole('option', { name: /^Kraken/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: "Créer l'actif" }))
    await settled()
    expect(toasts.map((t) => t.description)).toEqual(["Impossible de créer l'actif."])
  })

  it('enregistre la transaction dans la devise de l’utilisateur', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, preferredCurrency: 'USD' } })
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    await settled()
    expect(writes()[0].body).toMatchObject({ currency: 'USD' })
  })

  it.each([
    ['un ajout', async () => {
      const dialog = await openDialog(/Nouvelle/)
      await fillPurchase(dialog)
      calls.length = 0
      fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    }],
    ['un import', async () => {
      const dialog = await openImport()
      calls.length = 0
      fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    }],
  ])('relit la liste une seule fois après %s', async (_, act) => {
    await act()
    await settled()
    expect(listReads()).toBe(1)
  })

  it.each([
    ['l’ajout', /Nouvelle/, (dialog: HTMLElement) => within(dialog).getByRole('combobox', { name: 'Portefeuille' })],
    ['l’import', /Importer/, (dialog: HTMLElement) => within(dialog).getAllByRole('combobox')[0]],
  ])('ne propose pas le portefeuille de crowdfunding à %s', async (_, button, portfolioSelect) => {
    const dialog = await openDialog(button)
    expect(optionsOf(portfolioSelect(dialog))).toEqual(['Crypto', 'Bourse'])
  })

  it('liste les formats d’import annoncés par le serveur', async () => {
    const dialog = await openDialog(/Importer/)
    await within(dialog).findByText('OKX')
    expect(visibleText(dialog)).toContain('OKX')
  })

  it('écrit le nouveau solde au format français', async () => {
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    expect(visibleText(dialog)).toContain('0,52 BTC')
  })

  it('accorde au singulier une seule erreur, transaction ou ligne', async () => {
    routes['POST /transactions/import-csv'] = ok({
      success_count: 2,
      error_count: 1,
      skipped_count: 1,
      errors: ['Ligne 3 : symbole manquant'],
      created_transactions: ['n1', 'n2'],
    })
    const dialog = await openImport()
    fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    await settled()
    expect(toasts[0].description).toBe('2 transactions importées, 1 erreur. 1 déjà présente, ignorée.')
    expect(visibleText(dialog)).toContain('1 erreur')
    expect(visibleText(dialog)).not.toContain('1 erreurs')
  })
})
