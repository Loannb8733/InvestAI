import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { http } from '@/shared/api/http'
import { createFakeServer, ok, polyfillRadixPointer } from '@/test/fakeServer'
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
const count = (method: string, url: string) => calls.filter((c) => c.method === method && c.url === url).length
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

async function openPage() {
  renderWithQuery(<NotesPage />)
  await screen.findByText('Accumuler le BTC')
}

async function openForm(button: HTMLElement) {
  fireEvent.click(button)
  const dialog = await screen.findByRole('dialog')
  await settle(() => count('GET', '/assets') > 0)
  await within(dialog).findAllByRole('combobox')
  return dialog
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

describe('NotesPage — défauts corrigés', () => {
  it('un échec de création n’affiche qu’une notification', async () => {
    routes['POST /notes'] = () => ({ status: 500, data: { detail: 'indisponible' } })
    await openPage()
    const dialog = await openForm(screen.getByRole('button', { name: 'Nouvelle note' }))
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Idée' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => toasts.length > 0)
    await pause(50)
    expect(toasts).toEqual([{ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer la note.' }])
  })

  it('une modification peut vider le sentiment, le contenu et les tags', async () => {
    await openPage()
    const dialog = await openForm(screen.getAllByRole('button', { name: 'Modifier la note' })[0])
    fireEvent.change(within(dialog).getByLabelText('Contenu'), { target: { value: '' } })
    fireEvent.change(within(dialog).getByLabelText('Tags (séparés par des virgules)'), { target: { value: '' } })
    chooseOption(within(dialog).getAllByRole('combobox')[0], 'Aucun sentiment')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    await settle(() => count('PATCH', '/notes/n1') === 1)
    expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({ content: null, tags: null, sentiment: null })
  })

  it('« Charger plus » ajoute la page suivante sous la première', async () => {
    const page = (start: number, size: number) =>
      Array.from({ length: size }, (_, i) => ({ ...NOTE_PLAIN, id: `p${start + i}`, title: `Note ${start + i}` }))
    routes['GET /notes'] = (config) => ({ status: 200, data: config.params.skip === 0 ? page(0, 50) : page(50, 3) })
    renderWithQuery(<NotesPage />)
    await screen.findByText('Note 0')
    fireEvent.click(screen.getByRole('button', { name: 'Charger plus' }))
    await screen.findByText('Note 52')
    expect(screen.getByText('Note 0')).toBeInTheDocument()
  })

  it('la scorecard écrit les performances à la française', async () => {
    await openPage()
    fireEvent.click(screen.getByRole('button', { name: /Scorecard de vos analyses/ }))
    expect(await screen.findByText(/^\+4,3\s%$/)).toBeInTheDocument()
    expect(screen.getByText(/^-3,5\s%$/)).toBeInTheDocument()
  })

  it('la recherche n’interroge le serveur qu’une fois la frappe terminée', async () => {
    await openPage()
    const input = screen.getByPlaceholderText('Rechercher dans les notes...')
    for (const value of ['b', 'bt', 'btc']) fireEvent.change(input, { target: { value } })
    await settle(() => calls.some((c) => (c.params as { search?: string } | undefined)?.search === 'btc'))
    await pause(400)
    expect(calls.filter((c) => (c.params as { search?: string } | undefined)?.search).map((c) => c.params)).toEqual([
      { search: 'btc', skip: 0, limit: 50 },
    ])
  })

  it('la liste des actifs n’est chargée qu’à l’ouverture du formulaire', async () => {
    await openPage()
    await pause(50)
    expect(count('GET', '/assets')).toBe(0)
    await openForm(screen.getByRole('button', { name: 'Nouvelle note' }))
    expect(count('GET', '/assets')).toBe(1)
  })

  it('la suppression demande confirmation dans l’application, pas par le navigateur', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    await openPage()
    fireEvent.click(screen.getAllByRole('button', { name: 'Supprimer la note' })[0])
    const alert = await screen.findByRole('alertdialog')
    expect(within(alert).getByText(/Accumuler le BTC/)).toBeInTheDocument()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('un échec de chargement des notes affiche un état d’erreur, pas une liste vide', async () => {
    routes['GET /notes'] = () => ({ status: 500, data: { detail: 'boom' } })
    renderWithQuery(<NotesPage />)
    expect(await screen.findByText('Notes indisponibles')).toBeInTheDocument()
    expect(screen.queryByText('Aucune note')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /réessayer/i })).toBeInTheDocument()
    expect(toasts).toEqual([])
  })

  it('le résumé n’est rechargé qu’une fois après une création', async () => {
    await openPage()
    const before = count('GET', '/notes/summary')
    const dialog = await openForm(screen.getByRole('button', { name: 'Nouvelle note' }))
    fireEvent.change(within(dialog).getByLabelText('Titre *'), { target: { value: 'Idée' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Créer' }))
    await settle(() => count('GET', '/notes/summary') > before)
    await pause(100)
    expect(count('GET', '/notes/summary') - before).toBe(1)
  })

  it('le sélecteur d’actifs distingue les plateformes et ne répète pas le symbole', async () => {
    routes['GET /assets'] = ok([
      { id: 'k', symbol: 'BTC', name: 'Bitcoin', exchange: 'Kraken' },
      { id: 'b', symbol: 'BTC', name: 'Bitcoin', exchange: 'Binance' },
      { id: 'a', symbol: 'ADA', name: 'ADA', exchange: 'Kraken' },
    ])
    await openPage()
    const dialog = await openForm(screen.getByRole('button', { name: 'Nouvelle note' }))
    fireEvent.keyDown(within(dialog).getAllByRole('combobox')[1], { key: 'Enter' })
    const labels = screen.getAllByRole('option').map((option) => option.textContent)
    expect(labels).toEqual(['Aucun actif', 'BTC — Bitcoin · Kraken', 'BTC — Bitcoin · Binance', 'ADA · Kraken'])
  })
})
