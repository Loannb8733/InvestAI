import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { GAPS, NOW, exchangeRoutes, gapsFound, taskStatus } from '@/test/exchangeFixtures'
import { reduceMotion, renderWithQuery } from '@/test/render'
import ExchangesPage from './ExchangesPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = ({ action, ...props }: Record<string, unknown>) => {
    const element = action as { props: { altText: string; children: unknown } } | undefined
    toasts.push(element ? { ...props, action: { altText: element.props.altText, label: element.props.children } } : props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const failure = () => ({ status: 500, data: { detail: 'boom' } })
const sent = (route: string) => () => calls.some((c) => `${c.method} ${c.url}` === route)
const button = (name: string | RegExp, index = 0) => screen.getAllByRole('button', { name })[index]
const text = (root: Element | null) => (root?.textContent ?? '').replace(/\s+/g, ' ')
const panel = () => text(screen.getByText('Réconciliation', { selector: 'h3' }).closest('.border-border'))
const flat = (value: unknown) => String(value).replace(/\s+/g, ' ')

async function until(predicate: () => boolean) {
  for (let i = 0; i < 200 && !predicate(); i += 1) await pause(10)
  expect(predicate()).toBe(true)
  await pause(50)
}

async function open() {
  renderWithQuery(<ExchangesPage />)
  await screen.findByText('Exchanges supportés')
  await pause(50)
}

async function verifyGaps() {
  fireEvent.click(button(/Vérifier les écarts/))
  await screen.findByText('Valorisation estimée')
  await pause(50)
}

async function runTask(trigger: RegExp, statusRoute: string) {
  fireEvent.click(button(trigger))
  await vi.advanceTimersByTimeAsync(5000)
  await until(sent(statusRoute))
}

function addColdWallet() {
  fireEvent.change(document.getElementById('cw-address') as HTMLElement, { target: { value: 'bc1qnouvelle' } })
  fireEvent.change(document.getElementById('cw-label') as HTMLElement, { target: { value: 'Trezor' } })
  fireEvent.click(button('Ajouter'))
}

async function confirmDelete() {
  fireEvent.click(button(/Suppr\./, 1))
  fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'], now: NOW })
  server.reset(exchangeRoutes())
  toasts.length = 0
  reduceMotion()
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const FAILED_ACTIONS: Array<[string, string, () => unknown]> = [
  ['la synchronisation', 'POST /api-keys/k1/sync', () => fireEvent.click(button(/^Sync$/))],
  ['le test', 'POST /api-keys/k1/test', () => fireEvent.click(button(/Tester/))],
  ['la désactivation', 'PATCH /api-keys/k1', () => fireEvent.click(screen.getAllByTitle('Cliquer pour désactiver cette connexion')[0])],
  ['la suppression', 'DELETE /api-keys/k2', confirmDelete],
  ['le lancement de l’import', 'POST /api-keys/k1/import-async', () => fireEvent.click(button(/^Import$/))],
  ['le recalcul des taux', 'POST /api-keys/k1/refresh-fx', () => fireEvent.click(button(/Recalculer les taux de change/))],
  ['la vérification des écarts', 'GET /transactions/balance-gaps', () => fireEvent.click(button(/Vérifier les écarts/))],
  ['l’ajout d’un cold wallet', 'POST /cold-wallets', addColdWallet],
  ['la suppression d’un cold wallet', 'DELETE /cold-wallets/w1', () => fireEvent.click(button('Supprimer Ledger'))],
]

describe('exchanges — défauts corrigés', () => {
  it.each(FAILED_ACTIONS)('une seule notification, avec la raison du serveur, quand %s échoue', async (_label, route, act) => {
    routes[route] = failure
    await open()
    await act()
    await until(sent(route))
    expect(toasts).toEqual([expect.objectContaining({ variant: 'destructive', description: 'boom' })])
  })

  it.each([
    ['clés', 'GET /api-keys', /Impossible de charger vos clés API/],
    ['plateformes', 'GET /api-keys/exchanges', /Liste des plateformes indisponible/],
    ['cold wallets', 'GET /cold-wallets', /Impossible de charger les cold wallets/],
  ])('aucune notification quand la liste des %s échoue : la page le dit déjà', async (_label, route, message) => {
    routes[route] = failure
    renderWithQuery(<ExchangesPage />)
    await screen.findByText(message)
    await pause(100)
    expect(toasts).toEqual([])
  })

  it('montre la raison du serveur quand le crédit auto échoue', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    routes['POST /transactions/balance-gaps/credit-all'] = () => ({ status: 500, data: { detail: 'Prix du marché indisponible' } })
    await open()
    await verifyGaps()
    fireEvent.click(button(/Créditer en airdrop/))
    await until(sent('POST /transactions/balance-gaps/credit-all'))
    expect(toasts).toEqual([
      { variant: 'destructive', title: 'Erreur lors du crédit auto', description: 'Prix du marché indisponible' },
    ])
  })

  it('signale une seule fois l’échec de la vérification qui suit un import', async () => {
    routes['GET /api-keys/import-status/task-import'] = taskStatus('task-import', { status: 'completed', synced: 2 })
    routes['GET /transactions/balance-gaps'] = failure
    await open()
    await runTask(/^Import$/, 'GET /api-keys/import-status/task-import')
    await until(sent('GET /transactions/balance-gaps'))
    expect(toasts.filter((t) => t.variant === 'destructive')).toEqual([
      { variant: 'destructive', title: 'Erreur', description: 'boom' },
    ])
  })

  it('nomme les connexions même quand la liste des plateformes échoue', async () => {
    routes['GET /api-keys/exchanges'] = failure
    renderWithQuery(<ExchangesPage />)
    await screen.findByText('Liste des plateformes indisponible')
    const lines = visibleText()
    expect(lines).toEqual(expect.arrayContaining(['Binance', 'Kraken', 'OKX']))
    expect(lines).not.toEqual(expect.arrayContaining(['binance']))
    expect(lines).not.toEqual(expect.arrayContaining(['okx']))
  })

  it('propose de recharger les cold wallets après un échec', async () => {
    const wallets = routes['GET /cold-wallets']
    routes['GET /cold-wallets'] = failure
    await open()
    routes['GET /cold-wallets'] = wallets
    fireEvent.click(button('Réessayer'))
    expect(await screen.findByText('bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh')).toBeTruthy()
  })

  it('écrit montants et quantités à la française dans la réconciliation', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    await open()
    await verifyGaps()
    const content = panel()
    expect(content).toContain('4 récompenses non tracées détectées — total estimé 1 330,02 €.')
    for (const value of ['+0,2655', '142,37 €', '+40', '31,20 €', '+0,00000412', '+1 250', '1 150,40 €']) {
      expect(content).toContain(value)
    }
    expect(content).not.toMatch(/\d\.\d/)
  })

  it('écrit les soldes détectés à la française', async () => {
    await open()
    fireEvent.click(button(/Tester/))
    const dialog = text(await screen.findByRole('dialog'))
    expect(dialog).toContain('Soldes détectés (5 actifs)')
    for (const value of ['1 520 000', '2,5', '1,5', '0,512346', '0,000004']) expect(dialog).toContain(value)
    expect(dialog).not.toMatch(/\d\.\d|\de-\d/)
  })

  it('accorde au singulier les notifications et la réconciliation', async () => {
    routes['POST /api-keys/k1/sync'] = ok({ message: 'ok', synced_assets: 1, portfolio_id: 'p1', portfolio_name: 'Crypto' })
    routes['POST /api-keys/k1/test'] = ok({ success: true, message: 'ok', balance: { BTC: 0.5 } })
    routes['GET /transactions/balance-gaps'] = ok({ count: 1, threshold_eur: 5, gaps: GAPS.slice(0, 1) })
    routes['POST /transactions/balance-gaps/credit-all'] = ok({ credited: 1, skipped: 1, details: { credited: [], skipped: [] } })
    await open()
    fireEvent.click(button(/^Sync$/))
    await until(sent('POST /api-keys/k1/sync'))
    await verifyGaps()
    fireEvent.click(button(/Créditer en airdrop/))
    await until(sent('POST /transactions/balance-gaps/credit-all'))
    expect(panel()).toContain('1 récompense non tracée détectée — total estimé')
    fireEvent.click(button(/Tester/))
    expect(text(await screen.findByRole('dialog'))).toContain('Soldes détectés (1 actif)')
    expect(toasts).toEqual(
      expect.arrayContaining([
        { title: 'Synchronisation réussie', description: '1 actif synchronisé.' },
        { title: '1 récompense créditée en AIRDROP', description: '1 ignorée (déjà créditées ou prix marché manquant).' },
      ])
    )
  })

  it('accorde au singulier les tâches de fond', async () => {
    routes['GET /api-keys/import-status/task-import'] = taskStatus('task-import', { status: 'completed', synced: 1 })
    routes['GET /api-keys/import-status/task-fx'] = taskStatus('task-fx', { status: 'completed', synced: 1 })
    await open()
    await runTask(/^Import$/, 'GET /api-keys/import-status/task-import')
    await runTask(/Recalculer les taux de change/, 'GET /api-keys/import-status/task-fx')
    expect(toasts).toEqual(
      expect.arrayContaining([
        { title: 'Import réussi', description: '1 transaction synchronisée' },
        { title: 'Recalcul terminé', description: '1 transaction corrigée' },
      ])
    )
  })

  it('propose de « Créditer auto », accentué, avec un résumé à la française', async () => {
    routes['GET /api-keys/import-status/task-import'] = taskStatus('task-import', { status: 'completed', synced: 1 })
    routes['GET /transactions/balance-gaps'] = gapsFound
    await open()
    await runTask(/^Import$/, 'GET /api-keys/import-status/task-import')
    await until(sent('GET /transactions/balance-gaps'))
    const offer = toasts.find((t) => t.action) as Record<string, unknown>
    expect(offer.title).toBe('4 récompenses non tracées détectées')
    expect(flat(offer.description)).toBe(
      'Total estimé : 1 330,02 €. Top : BNB (142,37 €), ARB (31,20 €), DOT (6,05 €). (probables intérêts Earn)'
    )
    expect(offer.action).toEqual({ altText: 'Créditer automatiquement les récompenses en AIRDROP', label: 'Créditer auto' })
  })
})
