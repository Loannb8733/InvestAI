import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { http } from '@/shared/api/http'
import NotesPage from './NotesPage'

type Call = { method: string; url: string; params?: unknown; body?: unknown }
type Reply = { status: number; data?: unknown }
type Handler = (config: InternalAxiosRequestConfig) => Reply

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const NOTE_BTC = {
  id: 'n1',
  title: 'Accumuler le BTC',
  content: 'Achat progressif sous 60 000.',
  tags: 'crypto, long terme',
  asset_id: 'a1',
  asset_symbol: 'BTC',
  asset_name: 'Bitcoin',
  transaction_ids: null,
  attachments: null,
  sentiment: 'bullish',
  created_at: '2026-03-04T09:15:00Z',
  updated_at: '2026-03-04T09:15:00Z',
}

const NOTE_PLAIN = {
  id: 'n2',
  title: 'Revue trimestrielle',
  content: null,
  tags: null,
  asset_id: null,
  asset_symbol: null,
  asset_name: null,
  transaction_ids: null,
  attachments: null,
  sentiment: null,
  created_at: '2026-01-15T18:00:00Z',
  updated_at: '2026-01-15T18:00:00Z',
}

const SUMMARY = { total_notes: 2, notes_this_month: 1, unique_tags: ['crypto', 'long terme'] }

const ASSETS = [
  { id: 'a1', symbol: 'BTC', name: 'Bitcoin' },
  { id: 'a2', symbol: 'ETH', name: null },
]

const SCORECARD = {
  entries: [
    {
      note_id: 'n1',
      title: 'Accumuler le BTC',
      symbol: 'BTC',
      sentiment: 'bullish',
      note_date: '2026-03-04T09:15:00Z',
      perf_30d: 4.25,
      perf_90d: -3.5,
      verdict_30d: 'correct',
      verdict_90d: 'incorrect',
    },
    {
      note_id: 'n3',
      title: 'Prudence sur ETH',
      symbol: 'ETH',
      sentiment: 'neutral',
      note_date: '2026-05-20T10:00:00Z',
      perf_30d: 0,
      perf_90d: null,
      verdict_30d: 'correct',
      verdict_90d: 'pending',
    },
  ],
  summary: {
    total_scored: 2,
    unscorable: 1,
    hit_rate_30d: 100,
    hit_rate_90d: 0,
    by_sentiment: { bullish: { n: 1, hit_rate: 50 }, neutral: { n: 1, hit_rate: null } },
  },
}

let calls: Call[]
let routes: Record<string, Handler>

const ok = (data: unknown): Handler => () => ({ status: 200, data })

function defaultRoutes(): Record<string, Handler> {
  return {
    'GET /notes': ok([NOTE_BTC, NOTE_PLAIN]),
    'GET /notes/summary': ok(SUMMARY),
    'GET /assets': ok(ASSETS),
    'GET /notes/scorecard': ok(SCORECARD),
    'POST /notes': (config) => ({ status: 201, data: { ...NOTE_PLAIN, id: 'n9', ...JSON.parse(String(config.data)) } }),
    'PATCH /notes/n1': (config) => ({ status: 200, data: { ...NOTE_BTC, ...JSON.parse(String(config.data)) } }),
    'DELETE /notes/n1': () => ({ status: 204 }),
  }
}

const fakeServer: AxiosAdapter = async (config) => {
  const method = (config.method ?? 'get').toUpperCase()
  const url = config.url ?? ''
  const call: Call = { method, url }
  if (config.params && Object.keys(config.params).length > 0) call.params = config.params
  if (config.data !== undefined) call.body = JSON.parse(String(config.data))
  calls.push(call)
  const handler = routes[`${method} ${url}`]
  const reply = handler ? handler(config) : { status: 404, data: { detail: 'Not Found' } }
  const response = {
    data: reply.data ?? '',
    status: reply.status,
    statusText: String(reply.status),
    headers: new AxiosHeaders(),
    config,
  }
  if (reply.status >= 400) {
    throw new AxiosError(`Request failed with status code ${reply.status}`, 'ERR_BAD_RESPONSE', config, null, response)
  }
  return response
}

function visibleText(): string[] {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const lines: string[] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent?.replace(/\s+/g, ' ').trim()
    if (text) lines.push(text)
  }
  return lines
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <NotesPage />
    </QueryClientProvider>
  )
}

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/journal/${name}.json`)
}

async function settle(predicate: () => boolean) {
  await waitFor(() => expect(predicate()).toBe(true))
}

function requested(method: string, url: string) {
  return calls.some((c) => c.method === method && c.url === url)
}

function chooseOption(combobox: HTMLElement, name: string) {
  fireEvent.keyDown(combobox, { key: 'Enter' })
  fireEvent.keyDown(screen.getByRole('option', { name }), { key: 'Enter' })
}

beforeAll(() => {
  process.env.TZ = 'UTC'
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => {}
  Element.prototype.scrollIntoView ??= () => {}
  http.defaults.adapter = fakeServer
})

beforeEach(() => {
  calls = []
  routes = defaultRoutes()
  toasts.length = 0
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('NotesPage — caractérisation', () => {
  it('affiche le résumé, les tags et les notes', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    await golden('chargement', { calls, text: visibleText() })
  })

  it('montre un état vide sans note', async () => {
    routes['GET /notes'] = ok([])
    renderPage()
    await screen.findByText('Aucune note')
    await golden('liste_vide', { calls, text: visibleText() })
  })

  it('filtre par recherche puis par tag', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.change(screen.getByPlaceholderText('Rechercher dans les notes...'), { target: { value: 'btc' } })
    await settle(() => calls.some((c) => (c.params as { search?: string } | undefined)?.search === 'btc'))
    fireEvent.click(screen.getByText('long terme', { selector: '.cursor-pointer' }))
    await settle(() => calls.some((c) => (c.params as { tag?: string } | undefined)?.tag === 'long terme'))
    fireEvent.click(screen.getByText('Tous'))
    await settle(() => calls.filter((c) => JSON.stringify(c.params) === '{"search":"btc","skip":0,"limit":50}').length === 2)
    await golden('filtres', { calls })
  })

  it('charge la page suivante puis revient au début', async () => {
    const page = Array.from({ length: 50 }, (_, i) => ({ ...NOTE_PLAIN, id: `p${i}`, title: `Note ${i}` }))
    routes['GET /notes'] = ok(page)
    renderPage()
    await screen.findByText('Note 0')
    fireEvent.click(screen.getByRole('button', { name: 'Charger plus' }))
    await screen.findByRole('button', { name: 'Retour au début' })
    fireEvent.click(screen.getByRole('button', { name: 'Retour au début' }))
    await settle(() => !screen.queryByRole('button', { name: 'Retour au début' }))
    await settle(() => calls.filter((c) => c.url === '/notes').length === 3)
    await golden('pagination', { calls: calls.filter((c) => c.url === '/notes') })
  })

  it('déplie la scorecard', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    expect(requested('GET', '/notes/scorecard')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /Scorecard de vos analyses/ }))
    await screen.findByText('Prudence sur ETH')
    const card = screen.getByRole('table').closest('.space-y-4') as HTMLElement
    await golden('scorecard', {
      calls: calls.filter((c) => c.url === '/notes/scorecard'),
      text: within(card).getAllByText(/./).map((el) => el.textContent),
      verdicts: within(card).getAllByLabelText(/Correct|Incorrect|En attente/).map((el) => el.getAttribute('aria-label')),
    })
  })

  it('signale une scorecard indisponible', async () => {
    routes['GET /notes/scorecard'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getByRole('button', { name: /Scorecard de vos analyses/ }))
    await screen.findByText('Impossible de calculer la scorecard pour le moment.')
    await golden('scorecard_erreur', { toasts })
  })

  it('invite à lier des notes quand rien n’est évaluable', async () => {
    routes['GET /notes/scorecard'] = ok({
      entries: [],
      summary: { total_scored: 0, unscorable: 3, hit_rate_30d: null, hit_rate_90d: null, by_sentiment: {} },
    })
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getByRole('button', { name: /Scorecard de vos analyses/ }))
    const message = await screen.findByText(/Liez des notes à des actifs/)
    await golden('scorecard_vide', { text: message.textContent })
  })

  it('crée une note avec sentiment et actif lié', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getByRole('button', { name: 'Nouvelle note' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Rotation vers ETH' } })
    fireEvent.change(within(dialog).getByLabelText('Contenu'), { target: { value: 'Ratio ETH/BTC bas.' } })
    fireEvent.change(within(dialog).getByLabelText('Tags (séparés par des virgules)'), { target: { value: 'crypto' } })
    const [sentiment, asset] = within(dialog).getAllByRole('combobox')
    chooseOption(sentiment, 'Bearish')
    chooseOption(asset, 'ETH')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await settle(() => !screen.queryByRole('dialog'))
    await golden('creation', { calls: calls.filter((c) => c.method !== 'GET'), toasts })
  })

  it('crée une note minimale sans sentiment ni actif', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getByRole('button', { name: 'Nouvelle note' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Idée' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => requested('POST', '/notes'))
    await golden('creation_minimale', { calls: calls.filter((c) => c.method !== 'GET') })
  })

  it('signale un échec de création et garde le formulaire ouvert', async () => {
    routes['POST /notes'] = () => ({ status: 500, data: { detail: 'indisponible' } })
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getByRole('button', { name: 'Nouvelle note' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Idée' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length >= 2)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await golden('creation_echec', { toasts })
  })

  it('modifie une note et délie son actif', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getAllByRole('button', { name: 'Modifier la note' })[0])
    const dialog = await screen.findByRole('dialog')
    const form = {
      title: (within(dialog).getByLabelText('Titre *') as HTMLInputElement).value,
      content: (within(dialog).getByLabelText('Contenu') as HTMLTextAreaElement).value,
      tags: (within(dialog).getByLabelText('Tags (séparés par des virgules)') as HTMLInputElement).value,
      selects: within(dialog).getAllByRole('combobox').map((el) => el.textContent),
    }
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Accumuler le BTC (révisé)' } })
    chooseOption(within(dialog).getAllByRole('combobox')[1], 'Aucun actif')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    await settle(() => toasts.length > 0)
    await golden('modification', { form, calls: calls.filter((c) => c.method !== 'GET'), toasts })
  })

  it('supprime une note seulement après confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer la note' })[0])
    expect(requested('DELETE', '/notes/n1')).toBe(false)
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer la note' })[0])
    await settle(() => toasts.length > 0)
    await golden('suppression', {
      confirmations: confirm.mock.calls,
      calls: calls.filter((c) => c.method !== 'GET'),
      toasts,
    })
  })
})
