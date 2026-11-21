import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import RiskPerformancePillar from '@/components/intelligence/RiskPerformancePillar'
import { http } from '@/shared/api/http'
import { EMPTY_GLOBAL, NOW, analyticsRoutes, singleAsset, withGlobalWarning } from '@/test/analyticsFixtures'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { chooseOption, reduceMotion, renderWithQuery } from '@/test/render'

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
const failure = () => ({ status: 500, data: { detail: 'boom' } })
const count = (route: string) => calls.filter((c) => `${c.method} ${c.url}` === route).length
const called = (route: string) => () => count(route) > 0
const shown = (text: string) => () => screen.queryByText(text) !== null
const combobox = (name: string) => screen.getByRole('combobox', { name })

const SECONDARY = [
  'GET /analytics/diversification',
  'GET /analytics/correlation',
  'GET /analytics/performance',
  'GET /analytics/monte-carlo',
  'GET /analytics/xirr',
  'GET /analytics/optimize',
  'GET /analytics/stress-test',
  'GET /analytics/beta',
  'GET /dashboard/historical-data',
]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/analytics/${name}.json`)
}

async function until(predicate: () => boolean) {
  for (let i = 0; i < 500 && !predicate(); i += 1) await pause(10)
  expect(predicate()).toBe(true)
  await pause(100)
}

async function open(ready: () => boolean = called('GET /analytics/beta')) {
  const view = renderWithQuery(<RiskPerformancePillar />)
  await until(ready)
  return view.container
}

async function after(change: () => void, route: string) {
  calls.length = 0
  change()
  await until(called(route))
  return [...calls]
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: NOW })
  server.reset(analyticsRoutes())
  toasts.length = 0
  reduceMotion()
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Risque & Performance — chargement', () => {
  it('affiche le pilier complet', async () => {
    const container = await open()
    await golden('vue_complete', { calls, toasts, text: visibleText(container) })
  })

  it('invite à ajouter des actifs quand il n’y en a aucun', async () => {
    routes['GET /analytics'] = ok(EMPTY_GLOBAL)
    const container = await open(called('GET /smart-insights/health'))
    await golden('aucun_actif', { calls, toasts, text: visibleText(container) })
  })

  it('signale des analyses indisponibles', async () => {
    routes['GET /analytics'] = failure
    const container = await open(shown('Erreur de chargement'))
    await golden('analyses_indisponibles', { calls, toasts, text: visibleText(container) })
  })

  it('signale un score de santé indisponible puis le recharge', async () => {
    routes['GET /smart-insights/health'] = failure
    const container = await open()
    const section = visibleText(container).slice(0, 12)
    const retry = await after(() => fireEvent.click(screen.getByRole('button', { name: /Réessayer/ })), 'GET /smart-insights/health')
    await golden('sante_indisponible', { toasts, section, retry })
  })

  it('montre ce qui reste quand les analyses annexes échouent', async () => {
    for (const route of SECONDARY) routes[route] = failure
    const retried = SECONDARY.filter((route) => route.startsWith('GET /analytics/'))
    const container = await open(() => retried.every((route) => count(route) === 2) && shown('CSV')())
    await golden('annexes_indisponibles', { calls, toasts, text: visibleText(container) })
  })

  it('affiche l’avertissement global du serveur', async () => {
    routes['GET /analytics'] = ok(withGlobalWarning)
    const container = await open()
    const text = visibleText(container)
    const warning = text.indexOf(withGlobalWarning.interpretations.global)
    await golden('avertissement_global', { text: text.slice(warning - 1, warning + 3) })
  })

  it('n’optimise pas un portefeuille à un seul actif', async () => {
    routes['GET /analytics'] = ok(singleAsset)
    const container = await open()
    const text = visibleText(container)
    const start = text.indexOf('Optimisation & rééquilibrage')
    await golden('un_seul_actif', { calls, optimization: text.slice(start, start + 40) })
  })
})

describe('Risque & Performance — sélecteurs', () => {
  it('relit tout le pilier sur sept jours', async () => {
    await open()
    const requests = await after(() => chooseOption(combobox("Période d'analyse"), '7 jours'), 'GET /smart-insights/health')
    await golden('periode_7j', { calls: requests })
  })

  it('analyse un seul portefeuille', async () => {
    await open()
    fireEvent.keyDown(combobox('Portefeuille analysé'), { key: 'Enter' })
    const options = screen.getAllByRole('option').map((option) => option.textContent)
    const requests = await after(
      () => fireEvent.keyDown(screen.getByRole('option', { name: 'Crypto' }), { key: 'Enter' }),
      'GET /analytics/beta'
    )
    await golden('portefeuille', { options, calls: requests })
  })

  it('projette Monte Carlo sur un an', async () => {
    await open(called('GET /analytics/monte-carlo'))
    await until(() => screen.queryByRole('combobox', { name: 'Horizon de projection Monte Carlo' }) !== null)
    const requests = await after(
      () => chooseOption(combobox('Horizon de projection Monte Carlo'), '365 jours'),
      'GET /analytics/monte-carlo'
    )
    await golden('horizon_monte_carlo', { calls: requests })
  })
})
