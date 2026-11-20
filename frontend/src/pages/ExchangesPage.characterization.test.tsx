import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { resetAuth, SIGNED_IN_USER } from '@/test/identityFixtures'
import { EXCHANGES, NOW, exchangeRoutes } from '@/test/exchangeFixtures'
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
const card = (title: string) => screen.getByText(title, { selector: 'h3' }).closest('.border-border') as HTMLElement
const coldWalletCalls = () => calls.filter((c) => c.url.startsWith('/cold-wallets'))
const guideButton = (name: string) =>
  screen.getAllByRole('button', { name: /Voir le guide de connexion/ }).find((b) => b.textContent?.includes(name)) as HTMLElement

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/exchanges/${name}.json`)
}

async function open() {
  renderWithQuery(<ExchangesPage />)
  await screen.findByText('Exchanges supportés')
  await pause(50)
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

describe('Exchanges — page', () => {
  it('affiche les connexions, les wallets et les plateformes', async () => {
    await open()
    await golden('liste', { calls, toasts, text: visibleText() })
  })

  it('propose une première connexion', async () => {
    routes['GET /api-keys'] = ok([])
    await open()
    await golden('aucune_connexion', { calls, toasts, text: visibleText() })
  })

  it('réagit à des clés indisponibles', async () => {
    routes['GET /api-keys'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<ExchangesPage />)
    await screen.findByText('Impossible de charger vos clés API')
    await pause(50)
    await golden('cles_indisponibles', { calls, toasts, text: visibleText() })
  })

  it('recharge les clés après un échec', async () => {
    routes['GET /api-keys'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<ExchangesPage />)
    fireEvent.click(await screen.findByRole('button', { name: /Réessayer/ }))
    routes['GET /api-keys'] = ok([])
    await screen.findByText('Aucun exchange connecté')
    await pause(50)
    await golden('cles_rechargees', { calls, toasts })
  })

  it('cantonne l’échec des plateformes à sa carte', async () => {
    routes['GET /api-keys/exchanges'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<ExchangesPage />)
    await screen.findByText('Liste des plateformes indisponible')
    await pause(50)
    await golden('plateformes_indisponibles', { calls, toasts, text: visibleText() })
  })
})

describe('Exchanges — guides', () => {
  it('ouvre le guide d’une plateforme puis le formulaire de connexion', async () => {
    await open()
    fireEvent.click(guideButton('Kraken'))
    const guide = visibleText(await screen.findByRole('dialog'))
    fireEvent.click(screen.getByRole('button', { name: /Connecter Kraken/ }))
    await screen.findByText('Entrez vos clés API pour connecter votre exchange.', { exact: false })
    await pause(20)
    await golden('guide', { guide, form: visibleText(screen.getByRole('dialog')) })
  })

  it('prévient quand une plateforme n’a pas de guide', async () => {
    routes['GET /api-keys/exchanges'] = ok([
      ...EXCHANGES,
      { id: 'bitget', name: 'Bitget', requires_secret: true, requires_passphrase: true, description: 'Exchange de dérivés' },
    ])
    await open()
    fireEvent.click(guideButton('Bitget'))
    await golden('guide_absent', { dialog: visibleText(await screen.findByRole('dialog')) })
  })
})

describe('Exchanges — cold wallets', () => {
  it('nomme une adresse de retrait', async () => {
    await open()
    fireEvent.change(screen.getByLabelText('Adresse de retrait'), { target: { value: '  bc1qnouvelleadresse  ' } })
    fireEvent.change(screen.getByLabelText('Nom du wallet'), { target: { value: ' Trezor ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }))
    await settle(() => coldWalletCalls().length > 2)
    await pause(50)
    await golden('cold_wallet_ajout', { calls: coldWalletCalls(), toasts, card: visibleText(card('Cold wallets')) })
  })

  it('retire un cold wallet', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer Ledger' }))
    await settle(() => coldWalletCalls().length > 2)
    await pause(50)
    await golden('cold_wallet_suppression', { calls: coldWalletCalls(), toasts })
  })

  it('signale un cold wallet refusé', async () => {
    routes['POST /cold-wallets'] = () => ({ status: 422, data: { detail: 'Adresse invalide' } })
    await open()
    fireEvent.change(screen.getByLabelText('Adresse de retrait'), { target: { value: 'abc' } })
    fireEvent.change(screen.getByLabelText('Nom du wallet'), { target: { value: 'Ledger' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    await golden('cold_wallet_refuse', { calls: coldWalletCalls(), toasts, card: visibleText(card('Cold wallets')) })
  })

  it('réagit à des cold wallets indisponibles', async () => {
    routes['GET /cold-wallets'] = () => ({ status: 500, data: { detail: 'boom' } })
    await open()
    await screen.findByText(/Impossible de charger les cold wallets/)
    await golden('cold_wallets_indisponibles', { toasts, card: visibleText(card('Cold wallets')) })
  })
})
