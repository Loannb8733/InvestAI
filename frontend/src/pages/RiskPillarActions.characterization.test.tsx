import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import RiskPerformancePillar from '@/components/intelligence/RiskPerformancePillar'
import { http } from '@/shared/api/http'
import { BEARISH_HEALTH, NOW, analyticsRoutes } from '@/test/analyticsFixtures'
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
const button = (name: string | RegExp, index = 0) => screen.getAllByRole('button', { name })[index]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/analytics/${name}.json`)
}

async function until(predicate: () => boolean) {
  for (let i = 0; i < 500 && !predicate(); i += 1) await pause(10)
  expect(predicate()).toBe(true)
  await pause(100)
}

let container: HTMLElement

async function open() {
  container = renderWithQuery(<RiskPerformancePillar />).container
  await until(called('GET /analytics/beta'))
  calls.length = 0
}

function section(start: string, end: string) {
  const text = visibleText(container)
  const from = text.indexOf(start)
  return text.slice(from, text.indexOf(end, from + 1))
}

const markowitz = () => section('Optimisation & rééquilibrage', 'MPT Smart Insights')
const mpt = () => section('MPT Smart Insights', 'Évolution du portefeuille')

async function rebalance() {
  await open()
  fireEvent.click(button('Générer les ordres de rééquilibrage'))
  await until(called('POST /analytics/rebalance'))
}

async function plan() {
  await open()
  fireEvent.click(button('Planifier', 1))
  await until(called('POST /predictions/planned-orders'))
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

describe('Risque & Performance — optimisation', () => {
  it('optimise pour la volatilité minimale', async () => {
    await open()
    chooseOption(screen.getByRole('combobox', { name: "Objectif d'optimisation" }), 'Volatilité min')
    await until(called('GET /analytics/optimize'))
    await golden('objectif_volatilite_min', { calls, markowitz: markowitz() })
  })

  it('génère les ordres de rééquilibrage vers les poids optimaux', async () => {
    await rebalance()
    await golden('reequilibrage', { calls, toasts, markowitz: markowitz() })
  })

  it('signale des ordres de rééquilibrage impossibles', async () => {
    routes['POST /analytics/rebalance'] = failure
    await rebalance()
    await golden('reequilibrage_refuse', { toasts, markowitz: markowitz() })
  })

  it('planifie un ordre MPT', async () => {
    await plan()
    await golden('planifier', { calls, toasts, mpt: mpt() })
  })

  it('signale un ordre MPT impossible à planifier', async () => {
    routes['POST /predictions/planned-orders'] = failure
    await plan()
    await golden('planifier_refuse', { toasts, mpt: mpt() })
  })

  it('adapte les libellés d’action en marché baissier', async () => {
    routes['GET /smart-insights/health'] = ok(BEARISH_HEALTH)
    await open()
    await golden('mode_baissier', { mpt: mpt() })
  })
})

describe('Risque & Performance — actions', () => {
  it('exporte les métriques par actif en CSV', async () => {
    const blobs: Blob[] = []
    const downloads: string[] = []
    vi.spyOn(window.URL, 'createObjectURL').mockImplementation((blob) => {
      blobs.push(blob as Blob)
      return 'blob:faux'
    })
    vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push(this.download)
    })
    await open()
    fireEvent.click(button(/CSV/))
    const csv = await blobs[0].text()
    await golden('export_csv', { calls, downloads, type: blobs[0].type, lines: csv.split('\n') })
  })

  it('actualise le score de santé', async () => {
    await open()
    fireEvent.click(button('Actualiser le score de santé'))
    await until(called('GET /smart-insights/health'))
    await golden('actualiser_sante', { calls })
  })

  it('détaille un scénario de stress par actif', async () => {
    await open()
    fireEvent.click(button(/COVID-19/))
    fireEvent.click(button(/Détail par actif/))
    await pause(50)
    await golden('stress_scenario', { stress: section('Stress Tests Historiques', 'Beta vs Benchmark') })
  })
})
