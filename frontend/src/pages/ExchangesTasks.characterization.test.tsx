import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { NOW, exchangeRoutes, gapsFound, taskStatus } from '@/test/exchangeFixtures'
import { reduceMotion, renderWithQuery } from '@/test/render'
import ExchangesPage from './ExchangesPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)
const toastActions = vi.hoisted(() => [] as Array<() => void>)

vi.mock('@/hooks/use-toast', () => {
  const toast = ({ action, ...props }: Record<string, unknown>) => {
    const element = action as { props: { altText: string; children: unknown; onClick: () => void } } | undefined
    if (element) toastActions.push(element.props.onClick)
    toasts.push(element ? { ...props, action: { altText: element.props.altText, label: element.props.children } } : props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const taskCalls = () => calls.filter((c) => !['/api-keys', '/api-keys/exchanges', '/cold-wallets'].includes(c.url))
const count = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url).length
const panel = () => visibleText(screen.getByText('Réconciliation', { selector: 'h3' }).closest('.border-border') as HTMLElement)

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/exchanges/${name}.json`)
}

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

async function poll(url: string) {
  const before = count('GET', url)
  await vi.advanceTimersByTimeAsync(5000)
  await until(() => count('GET', url) > before)
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'], now: NOW })
  server.reset(exchangeRoutes())
  toasts.length = 0
  toastActions.length = 0
  reduceMotion()
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const IMPORT_STATUS = '/api-keys/import-status/task-import'

describe('Exchanges — import d’historique', () => {
  it('suit l’import jusqu’au bout et signale les récompenses non tracées', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /^Import$/ })[0])
    await until(() => count('POST', '/api-keys/k1/import-async') === 1)
    const launched = { toasts: [...toasts], disabled: (screen.getAllByRole('button', { name: /^Import$/ })[0] as HTMLButtonElement).disabled }
    await poll(IMPORT_STATUS)
    const pending = toasts.length
    await poll(IMPORT_STATUS)
    await until(() => count('GET', '/transactions/balance-gaps') === 1)
    await golden('import', { launched, pendingToasts: pending, calls: taskCalls(), toasts, panel: panel() })
  })

  it('crédite les récompenses depuis la notification', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    routes[`GET ${IMPORT_STATUS}`] = taskStatus('task-import', { status: 'completed', synced: 1 })
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /^Import$/ })[0])
    await poll(IMPORT_STATUS)
    await until(() => toastActions.length === 1)
    const before = calls.length
    toasts.length = 0
    toastActions[0]()
    await until(() => count('GET', '/transactions/balance-gaps') === 2)
    await golden('import_credit', { calls: calls.slice(before), toasts, panel: panel() })
  })

  it('signale un import échoué', async () => {
    routes[`GET ${IMPORT_STATUS}`] = taskStatus('task-import', { status: 'failed', error: 'Binance a refusé la signature' })
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /^Import$/ })[0])
    await poll(IMPORT_STATUS)
    await vi.advanceTimersByTimeAsync(5000)
    await pause(50)
    await golden('import_echoue', { calls: taskCalls(), toasts })
  })

  it('arrête le suivi quand le statut est illisible', async () => {
    routes[`GET ${IMPORT_STATUS}`] = () => ({ status: 500, data: { detail: 'boom' } })
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /^Import$/ })[0])
    await poll(IMPORT_STATUS)
    await vi.advanceTimersByTimeAsync(5000)
    await pause(50)
    await golden('import_statut_illisible', { calls: taskCalls(), toasts })
  })

  it('signale un import refusé', async () => {
    routes['POST /api-keys/k1/import-async'] = () => ({ status: 500, data: { detail: 'File Celery pleine' } })
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /^Import$/ })[0])
    await until(() => toasts.length > 0)
    await golden('import_refuse', { calls: taskCalls(), toasts })
  })

  it('recalcule les taux de change', async () => {
    await open()
    fireEvent.click(screen.getAllByRole('button', { name: /Recalculer les taux de change/ })[0])
    await until(() => count('POST', '/api-keys/k1/refresh-fx') === 1)
    await poll('/api-keys/import-status/task-fx')
    await until(() => count('GET', '/transactions/balance-gaps') === 1)
    await golden('recalcul_fx', { calls: taskCalls(), toasts, panel: panel() })
  })
})

describe('Exchanges — réconciliation', () => {
  it('ne trouve aucun écart', async () => {
    await open()
    const before = panel()
    fireEvent.click(screen.getByRole('button', { name: /Vérifier les écarts/ }))
    await until(() => count('GET', '/transactions/balance-gaps') === 1)
    await golden('reconciliation_vide', { before, calls: taskCalls(), toasts, panel: panel() })
  })

  it('liste les écarts puis les crédite en airdrop', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Vérifier les écarts/ }))
    await until(() => count('GET', '/transactions/balance-gaps') === 1)
    const gaps = panel()
    fireEvent.click(screen.getByRole('button', { name: /Créditer en airdrop/ }))
    await until(() => count('GET', '/transactions/balance-gaps') === 2)
    await golden('reconciliation_ecarts', { gaps, calls: taskCalls(), toasts, panel: panel() })
  })

  it('signale une vérification impossible', async () => {
    routes['GET /transactions/balance-gaps'] = () => ({ status: 500, data: { detail: 'boom' } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Vérifier les écarts/ }))
    await until(() => toasts.length > 0)
    await golden('reconciliation_refusee', { toasts, panel: panel() })
  })

  it('signale un crédit refusé', async () => {
    routes['GET /transactions/balance-gaps'] = gapsFound
    routes['POST /transactions/balance-gaps/credit-all'] = () => ({ status: 500, data: { detail: 'boom' } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Vérifier les écarts/ }))
    await until(() => count('GET', '/transactions/balance-gaps') === 1)
    fireEvent.click(screen.getByRole('button', { name: /Créditer en airdrop/ }))
    await until(() => toasts.length > 0)
    await golden('credit_refuse', { calls: taskCalls(), toasts })
  })
})
