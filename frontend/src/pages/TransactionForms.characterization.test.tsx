import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { transactionRoutes } from '@/test/transactionFixtures'
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
const writes = () => calls.filter((c) => c.method !== 'GET')
const reads = () => calls.filter((c) => c.method === 'GET').map((c) => c.url)
const field = (id: string) => document.getElementById(id) as HTMLInputElement
const type = (id: string, value: string) => fireEvent.change(field(id), { target: { value } })
const listDetail = [{ type: 'greater_than', loc: ['body', 'quantity'], msg: 'Input should be greater than 0' }]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/transactions/${name}.json`)
}

async function openDialog(button: RegExp) {
  renderWithQuery(<TransactionsPage />)
  await screen.findByText('Historique')
  await pause(50)
  fireEvent.click(screen.getByRole('button', { name: button }))
  return screen.findByRole('dialog')
}

async function pickPlatform(trigger: HTMLElement, name: RegExp) {
  fireEvent.click(trigger)
  fireEvent.click(await screen.findByRole('option', { name }))
}

async function fillPurchase(dialog: HTMLElement) {
  chooseOption(within(dialog).getByRole('combobox', { name: 'Portefeuille' }), 'Crypto')
  chooseOption(await within(dialog).findByRole('combobox', { name: 'Actif' }), 'BTC (Binance) - Bitcoin')
  type('quantity', '0.02')
  type('price', '50000')
  type('fee', '2')
  await pause(20)
}

async function afterWrite(predicate: () => boolean) {
  await settle(predicate)
  await pause(50)
  return { writes: writes(), reads: reads(), toasts }
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

describe('Nouvelle transaction', () => {
  it('enregistre un achat', async () => {
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    const text = visibleText(dialog)
    calls.length = 0
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    const result = await afterWrite(() => toasts.length > 0)
    await golden('ajout_achat', { text, ...result, open: screen.queryByRole('dialog') !== null })
  })

  it('enregistre un transfert sortant vers une destination', async () => {
    const dialog = await openDialog(/Nouvelle/)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Transfert sortant' }))
    await fillPurchase(dialog)
    await pickPlatform(within(dialog).getByRole('combobox', { name: 'Cold wallet, autre exchange...' }), /^Ledger/)
    const text = visibleText(dialog)
    calls.length = 0
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    const result = await afterWrite(() => toasts.length > 0)
    await golden('ajout_transfert_sortant', { text, writes: result.writes })
  })

  it('refuse une quantité nulle', async () => {
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    type('quantity', '0')
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    await within(dialog).findByText('Quantité doit être positive')
    await golden('ajout_invalide', { writes: writes(), text: visibleText(dialog) })
  })

  it('signale un ajout rejeté par la validation du serveur', async () => {
    routes['POST /transactions'] = () => ({ status: 422, data: { detail: listDetail } })
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('ajout_rejete_422', { toasts })
  })

  it('libelle les frais dans la devise de l’utilisateur', async () => {
    resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: { ...SIGNED_IN_USER, preferredCurrency: 'USD' } })
    const dialog = await openDialog(/Nouvelle/)
    await fillPurchase(dialog)
    const label = visibleText(field('fee').closest('div') as HTMLElement)
    calls.length = 0
    fireEvent.submit(dialog.querySelector('form') as HTMLFormElement)
    const result = await afterWrite(() => toasts.length > 0)
    await golden('ajout_devise_usd', { label, writes: result.writes })
  })

  it('crée un actif depuis le formulaire', async () => {
    const dialog = await openDialog(/Nouvelle/)
    chooseOption(within(dialog).getByRole('combobox', { name: 'Portefeuille' }), 'Crypto')
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Nouveau' }))
    fireEvent.change(within(dialog).getByPlaceholderText('BTC, AAPL...'), { target: { value: 'link' } })
    fireEvent.change(within(dialog).getByPlaceholderText('Bitcoin, Apple...'), { target: { value: 'Chainlink' } })
    await pickPlatform(within(dialog).getByRole('combobox', { name: 'Plateforme...' }), /^Kraken/)
    calls.length = 0
    fireEvent.click(within(dialog).getByRole('button', { name: "Créer l'actif" }))
    const result = await afterWrite(() => toasts.length > 0)
    await golden('ajout_nouvel_actif', { ...result, text: visibleText(dialog) })
  })

  it('signale un actif refusé par le serveur', async () => {
    routes['POST /assets'] = () => ({ status: 400, data: { detail: 'Cet actif existe déjà dans ce portefeuille' } })
    const dialog = await openDialog(/Nouvelle/)
    chooseOption(within(dialog).getByRole('combobox', { name: 'Portefeuille' }), 'Crypto')
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Nouveau' }))
    fireEvent.change(within(dialog).getByPlaceholderText('BTC, AAPL...'), { target: { value: 'btc' } })
    await pickPlatform(within(dialog).getByRole('combobox', { name: 'Plateforme...' }), /^Kraken/)
    fireEvent.click(within(dialog).getByRole('button', { name: "Créer l'actif" }))
    const result = await afterWrite(() => toasts.length > 0)
    await golden('ajout_actif_refuse', { writes: result.writes, toasts })
  })
})

describe('Import CSV', () => {
  async function openImport() {
    const dialog = await openDialog(/Importer/)
    const file = new File(['symbol;type\n'], 'binance.csv', { type: 'text/csv' })
    fireEvent.change(dialog.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } })
    return dialog
  }

  it('exige un portefeuille de destination', async () => {
    const dialog = await openImport()
    await golden('import_sans_portefeuille', {
      text: visibleText(dialog),
      disabled: (within(dialog).getByRole('button', { name: /Importer dans/ }) as HTMLButtonElement).disabled,
    })
  })

  it('importe un fichier', async () => {
    const dialog = await openImport()
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Crypto')
    calls.length = 0
    fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    const result = await afterWrite(() => toasts.length > 0)
    await golden('import_reussi', { ...result, open: screen.queryByRole('dialog') !== null })
  })

  it('montre les erreurs d’un import partiel', async () => {
    routes['POST /transactions/import-csv'] = ok({
      success_count: 2,
      error_count: 1,
      skipped_count: 4,
      errors: ['Ligne 3 : symbole manquant'],
      created_transactions: ['n1', 'n2'],
    })
    const dialog = await openImport()
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Crypto')
    chooseOption(within(dialog).getAllByRole('combobox')[1], 'Kraken')
    fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('import_partiel', { writes: writes(), toasts, text: visibleText(dialog) })
  })

  it('signale un fichier refusé', async () => {
    routes['POST /transactions/import-csv'] = () => ({ status: 400, data: { detail: 'Format de fichier non reconnu' } })
    const dialog = await openImport()
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Crypto')
    fireEvent.click(within(dialog).getByRole('button', { name: /Importer dans/ }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('import_refuse', { toasts })
  })
})
