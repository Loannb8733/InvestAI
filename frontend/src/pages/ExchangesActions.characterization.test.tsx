import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { NOW, exchangeRoutes } from '@/test/exchangeFixtures'
import { reduceMotion, renderWithQuery, settle } from '@/test/render'
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
const keyCalls = () => calls.filter((c) => c.url.startsWith('/api-keys') && c.url !== '/api-keys/exchanges')
const sent = (method: string, url: string) => () => calls.some((c) => c.method === method && c.url === url)
const button = (name: string | RegExp, index = 0) => screen.getAllByRole('button', { name })[index]

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/exchanges/${name}.json`)
}

async function open() {
  renderWithQuery(<ExchangesPage />)
  await screen.findByText('Exchanges supportés')
  await pause(50)
}

async function after(method: string, url: string) {
  await settle(sent(method, url))
  await pause(50)
}

async function openConnectForm(exchange: RegExp) {
  await open()
  fireEvent.click(button('Connecter un exchange'))
  const disabledBeforeChoice = (screen.getByRole('button', { name: 'Connecter' }) as HTMLButtonElement).disabled
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
  fireEvent.keyDown(screen.getByRole('option', { name: exchange }), { key: 'Enter' })
  await pause(20)
  return disabledBeforeChoice
}

function fill(fields: Record<string, string>) {
  for (const [id, value] of Object.entries(fields)) {
    fireEvent.change(document.getElementById(id) as HTMLElement, { target: { value } })
  }
}

beforeAll(() => {
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: NOW })
  server.reset(exchangeRoutes())
  toasts.length = 0
  reduceMotion()
  resetAuth({ isAuthenticated: true, accessToken: 'access-1', user: SIGNED_IN_USER })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Exchanges — connexion', () => {
  it('connecte une plateforme qui demande une passphrase', async () => {
    const disabledBeforeChoice = await openConnectForm(/OKX/)
    fill({ label: 'Trading', api_key: 'okx-key', secret_key: 'okx-secret', passphrase: 'okx-pass' })
    const form = visibleText(screen.getByRole('dialog'))
    fireEvent.click(screen.getByRole('button', { name: 'Connecter' }))
    await after('POST', '/api-keys')
    await golden('ajout', { disabledBeforeChoice, form, calls: keyCalls(), toasts, dialog: screen.queryByRole('dialog') !== null })
  })

  it('connecte une plateforme sans clé secrète, sans label', async () => {
    await openConnectForm(/Bitpanda/)
    fill({ api_key: 'bitpanda-key' })
    const form = visibleText(screen.getByRole('dialog'))
    fireEvent.click(screen.getByRole('button', { name: 'Connecter' }))
    await after('POST', '/api-keys')
    await golden('ajout_sans_secret', { form, calls: keyCalls().filter((c) => c.method === 'POST') })
  })

  it('signale une connexion refusée', async () => {
    routes['POST /api-keys'] = () => ({ status: 400, data: { detail: 'Clé API invalide pour Binance' } })
    await openConnectForm(/Binance/)
    fill({ api_key: 'bad', secret_key: 'bad' })
    fireEvent.click(screen.getByRole('button', { name: 'Connecter' }))
    await after('POST', '/api-keys')
    await golden('ajout_refuse', { toasts, dialog: screen.queryByRole('dialog') !== null })
  })
})

describe('Exchanges — modification', () => {
  it('renomme une connexion', async () => {
    await open()
    fireEvent.click(button('Renommer cette connexion'))
    const dialog = visibleText(await screen.findByRole('dialog'))
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: '  Compte DCA  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await after('PATCH', '/api-keys/k1')
    await golden('renommer', { dialog, calls: keyCalls(), toasts, open: screen.queryByRole('dialog') !== null })
  })

  it('désactive puis réactive une connexion', async () => {
    await open()
    fireEvent.click(screen.getAllByTitle('Cliquer pour désactiver cette connexion')[0])
    await after('PATCH', '/api-keys/k1')
    fireEvent.click(screen.getAllByTitle('Cliquer pour réactiver cette connexion')[0])
    await after('PATCH', '/api-keys/k3')
    await golden('activation', { calls: keyCalls(), toasts })
  })

  it('signale une modification refusée', async () => {
    routes['PATCH /api-keys/k1'] = () => ({ status: 500, data: { detail: 'Base indisponible' } })
    await open()
    fireEvent.click(screen.getAllByTitle('Cliquer pour désactiver cette connexion')[0])
    await after('PATCH', '/api-keys/k1')
    await golden('modification_refusee', { toasts })
  })
})

describe('Exchanges — suppression', () => {
  it('supprime une connexion après confirmation', async () => {
    await open()
    fireEvent.click(button(/Suppr\./, 1))
    const dialog = visibleText(await screen.findByRole('alertdialog'))
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer' }))
    await after('DELETE', '/api-keys/k2')
    await golden('suppression', { dialog, calls: keyCalls(), toasts })
  })

  it('signale une suppression refusée', async () => {
    routes['DELETE /api-keys/k2'] = () => ({ status: 500, data: { detail: 'boom' } })
    await open()
    fireEvent.click(button(/Suppr\./, 1))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    await after('DELETE', '/api-keys/k2')
    await golden('suppression_refusee', { toasts })
  })
})

describe('Exchanges — test et synchronisation', () => {
  it('teste une connexion et montre les soldes', async () => {
    await open()
    fireEvent.click(button(/Tester/))
    const dialog = visibleText(await screen.findByRole('dialog'))
    await pause(50)
    await golden('test_reussi', { calls: keyCalls(), toasts, dialog })
  })

  it('montre un test en échec', async () => {
    routes['POST /api-keys/k1/test'] = ok({ success: false, message: 'Signature invalide', balance: null })
    await open()
    fireEvent.click(button(/Tester/))
    const dialog = visibleText(await screen.findByRole('dialog'))
    await golden('test_echoue', { toasts, dialog })
  })

  it('signale un test impossible', async () => {
    routes['POST /api-keys/k1/test'] = () => ({ status: 500, data: { detail: 'Binance injoignable' } })
    await open()
    fireEvent.click(button(/Tester/))
    await after('POST', '/api-keys/k1/test')
    await golden('test_refuse', { toasts, dialog: screen.queryByRole('dialog') !== null })
  })

  it('synchronise les soldes', async () => {
    await open()
    fireEvent.click(button(/^Sync$/))
    await after('POST', '/api-keys/k1/sync')
    await golden('sync', { calls: keyCalls(), toasts })
  })

  it('signale une synchronisation refusée', async () => {
    routes['POST /api-keys/k1/sync'] = () => ({ status: 500, data: { detail: 'Binance indisponible' } })
    await open()
    fireEvent.click(button(/^Sync$/))
    await after('POST', '/api-keys/k1/sync')
    await golden('sync_refusee', { toasts })
  })
})
