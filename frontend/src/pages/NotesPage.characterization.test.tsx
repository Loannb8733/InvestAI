import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer, visibleText } from '@/test/fakeServer'
import { journalRoutes, NOTE_PLAIN } from '@/test/journalFixtures'
import { chooseOption, renderWithQuery, settle } from '@/test/render'
import NotesPage from './NotesPage'

const toasts = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/hooks/use-toast', () => {
  const toast = (props: Record<string, unknown>) => {
    toasts.push(props)
  }
  return { toast, useToast: () => ({ toast }) }
})

const server = createFakeServer()
const { calls, routes } = server

const renderPage = () => renderWithQuery(<NotesPage />)

async function golden(name: string, value: unknown) {
  await expect(`${JSON.stringify(value, null, 2)}\n`).toMatchFileSnapshot(`../__golden__/journal/${name}.json`)
}

function requested(method: string, url: string) {
  return calls.some((c) => c.method === method && c.url === url)
}

beforeAll(() => {
  process.env.TZ = 'UTC'
  polyfillRadixPointer()
  http.defaults.adapter = server.adapter
})

beforeEach(() => {
  server.reset(journalRoutes())
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
    await golden('filtres', { calls })
  })

  it('charge la page suivante à la suite de la première', async () => {
    const page = (start: number, count: number) =>
      Array.from({ length: count }, (_, i) => ({ ...NOTE_PLAIN, id: `p${start + i}`, title: `Note ${start + i}` }))
    routes['GET /notes'] = (config) => ({ status: 200, data: config.params.skip === 0 ? page(0, 50) : page(50, 3) })
    renderPage()
    await screen.findByText('Note 0')
    fireEvent.click(screen.getByRole('button', { name: 'Charger plus' }))
    await screen.findByText('Note 52')
    await golden('pagination', {
      calls: calls.filter((c) => c.url === '/notes'),
      shown: screen.getAllByRole('button', { name: 'Modifier la note' }).length,
      more: screen.queryByRole('button', { name: 'Charger plus' }) !== null,
    })
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
    await settle(() => requested('GET', '/assets'))
    await within(dialog).findAllByText('Aucun actif')
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
    await settle(() => toasts.length > 0)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await golden('creation_echec', { toasts })
  })

  it('modifie une note et délie son actif', async () => {
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getAllByRole('button', { name: 'Modifier la note' })[0])
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByText('BTC — Bitcoin')
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
    renderPage()
    await screen.findByText('Accumuler le BTC')
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer la note' })[0])
    const first = await screen.findByRole('alertdialog')
    const question = within(first).getAllByText(/./).map((el) => el.textContent)
    fireEvent.click(within(first).getByRole('button', { name: 'Annuler' }))
    await settle(() => !screen.queryByRole('alertdialog'))
    expect(requested('DELETE', '/notes/n1')).toBe(false)
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer la note' })[0])
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Supprimer' }))
    await settle(() => toasts.length > 0)
    await golden('suppression', { question, calls: calls.filter((c) => c.method !== 'GET'), toasts })
  })
})
