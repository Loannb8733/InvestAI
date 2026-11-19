import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
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
const blobs: Blob[] = []
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const failure = () => ({ status: 500, data: { detail: 'boom' } })
const writes = () => calls.filter((c) => c.method !== 'GET')
const reads = () => calls.filter((c) => c.method === 'GET').map((c) => c.url)
const rowMenu = (index: number) => screen.getAllByRole('button', { name: 'Actions sur la transaction' })[index]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/transactions/${name}.json`)
}

async function open() {
  renderWithQuery(<TransactionsPage />)
  await screen.findByText('Historique')
  await pause(50)
}

async function menuItem(trigger: HTMLElement, name: RegExp) {
  fireEvent.keyDown(trigger, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name }))
}

async function confirm(trigger: HTMLElement | Promise<void>, button: string) {
  if (trigger instanceof HTMLElement) fireEvent.click(trigger)
  else await trigger
  const dialog = await screen.findByRole('alertdialog')
  const text = visibleText(dialog)
  fireEvent.click(within(dialog).getByRole('button', { name: button }))
  return text
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
  blobs.length = 0
  reduceMotion()
  vi.spyOn(window.URL, 'createObjectURL').mockImplementation((blob) => {
    blobs.push(blob as Blob)
    return 'blob:faux'
  })
  vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Transactions — exports', () => {
  it('exporte tout depuis le serveur', async () => {
    await open()
    calls.length = 0
    await menuItem(screen.getByRole('button', { name: 'Exporter' }), /Tout exporter/)
    await settle(() => toasts.length > 0)
    await golden('export_serveur', { calls, toasts, files: blobs.length })
  })

  it('signale un export serveur refusé', async () => {
    routes['GET /transactions/export-csv'] = failure
    await open()
    await menuItem(screen.getByRole('button', { name: 'Exporter' }), /Tout exporter/)
    await settle(() => toasts.length > 0)
    await golden('export_serveur_refuse', { toasts, files: blobs.length })
  })

  it('exporte les lignes filtrées', async () => {
    await open()
    chooseOption(screen.getAllByRole('combobox')[2], 'Achats')
    await screen.findByText('Total achats (filtrés)')
    await pause(50)
    await menuItem(screen.getByRole('button', { name: 'Exporter' }), /Exporter filtrés/)
    await settle(() => toasts.length > 0)
    await golden('export_filtres', { toasts, csv: await blobs[0].text() })
  })

  it('exporte la sélection', async () => {
    await open()
    const boxes = screen.getAllByRole('checkbox')
    fireEvent.click(boxes[1])
    fireEvent.click(boxes[4])
    await pause(20)
    const bar = visibleText(screen.getByText(/sélectionnées/).parentElement as HTMLElement)
    fireEvent.click(within(screen.getByText(/sélectionnées/).parentElement as HTMLElement).getByRole('button', { name: 'Exporter' }))
    await settle(() => toasts.length > 0)
    await golden('export_selection', { bar, toasts, csv: await blobs[0].text() })
  })
})

describe('Transactions — suppressions', () => {
  it('supprime une transaction après confirmation', async () => {
    await open()
    const dialog = await confirm(menuItem(rowMenu(3), /Supprimer/), 'Supprimer')
    const result = await afterWrite(() => toasts.length > 0)
    await golden('suppression', { dialog, ...result })
  })

  it('signale une suppression refusée', async () => {
    routes['DELETE /transactions/t2'] = failure
    await open()
    await confirm(menuItem(rowMenu(3), /Supprimer/), 'Supprimer')
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('suppression_refusee', { toasts, dialog: screen.queryByRole('alertdialog') !== null })
  })

  it('supprime plusieurs transactions, une échoue', async () => {
    await open()
    const boxes = screen.getAllByRole('checkbox')
    fireEvent.click(boxes[1])
    fireEvent.click(boxes[2])
    fireEvent.click(boxes[3])
    const bar = screen.getByText(/sélectionnées/).parentElement as HTMLElement
    const dialog = await confirm(within(bar).getByRole('button', { name: 'Supprimer' }), 'Supprimer')
    const result = await afterWrite(() => toasts.some((t) => String(t.title).includes('supprimées')))
    await golden('suppression_multiple', { dialog, ...result })
  })

  it('supprime toutes les transactions', async () => {
    await open()
    const dialog = await confirm(screen.getByRole('button', { name: 'Tout supprimer' }), 'Supprimer tout')
    const result = await afterWrite(() => toasts.length > 0)
    await golden('tout_supprimer', { dialog, ...result })
  })

  it('filtre au-delà des deux cents lignes chargées', async () => {
    routes['GET /transactions'] = listTransactions(TRANSACTIONS, 250)
    await open()
    chooseOption(screen.getAllByRole('combobox')[2], 'Ventes')
    await screen.findByText('Total ventes (filtrés)')
    await pause(50)
    await golden('filtre_au_dela_du_chargement', { text: visibleText(screen.getByText('Historique').closest('.space-y-6') as HTMLElement) })
  })
})

describe('Transactions — modification', () => {
  async function openEdit() {
    await open()
    await menuItem(rowMenu(18), /Modifier/)
    return screen.findByRole('dialog')
  }

  const inputs = (dialog: HTMLElement) => dialog.querySelectorAll('input')

  it('pré-remplit le formulaire', async () => {
    const dialog = await openEdit()
    await golden('modification_formulaire', {
      text: visibleText(dialog),
      values: [...inputs(dialog)].map((input) => input.value),
    })
  })

  it('enregistre une nouvelle quantité', async () => {
    const dialog = await openEdit()
    calls.length = 0
    fireEvent.change(inputs(dialog)[2], { target: { value: '2.5' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    const result = await afterWrite(() => toasts.length > 0)
    await golden('modification', { ...result, open: screen.queryByRole('dialog') !== null })
  })

  it('enregistre sans rien changer', async () => {
    const dialog = await openEdit()
    calls.length = 0
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    const result = await afterWrite(() => toasts.length > 0)
    await golden('modification_inchangee', result)
  })

  it('signale une modification refusée', async () => {
    routes['PATCH /transactions/t1'] = failure
    const dialog = await openEdit()
    fireEvent.change(inputs(dialog)[2], { target: { value: '2.5' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('modification_refusee', { toasts, open: screen.queryByRole('dialog') !== null })
  })
})
