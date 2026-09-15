/**
 * Le service worker ne doit ni retarder un déploiement, ni salir la console.
 *
 * `public/sw.js` servait tout « cache d'abord », page d'entrée comprise :
 * comme index.html porte les noms hachés des scripts du déploiement courant,
 * le premier chargement après un déploiement montrait la version précédente,
 * et la nouvelle n'apparaissait qu'au chargement suivant. Et un `cache.put`
 * non rattrapé finissait en « Uncaught (in promise) TypeError » dès qu'une
 * réponse ne se laissait pas mémoriser (NEW-88).
 *
 * Le script est chargé tel quel dans un faux environnement de worker.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Mock } from 'vitest'

type Handler = (event: { request: Request; respondWith: (p: Promise<Response>) => void; waitUntil: (p: Promise<unknown>) => void }) => void

function reponse(texte: string, status = 200): Response {
  return new Response(texte, { status })
}

// Le constructeur Request de jsdom refuse `mode: 'navigate'` : une navigation
// est représentée par l'objet minimal que le worker consulte.
function navigation(url: string): Request {
  return { url, method: 'GET', mode: 'navigate' } as unknown as Request
}

function chargerWorker(caches: unknown, fetchImpl: unknown) {
  const handlers: Record<string, Handler> = {}
  const self = {
    addEventListener: (nom: string, h: Handler) => {
      handlers[nom] = h
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  }
  const source = readFileSync(resolve(__dirname, '../../public/sw.js'), 'utf8')
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  new Function('self', 'caches', 'fetch', source)(self, caches, fetchImpl)
  return handlers
}

async function servir(handlers: Record<string, Handler>, request: Request): Promise<Response | undefined> {
  let promesse: Promise<Response> | undefined
  handlers.fetch({ request, respondWith: (p) => (promesse = p), waitUntil: () => {} })
  return promesse
}

describe('service worker', () => {
  let enCache: Map<string, Response>
  let put: Mock<[Request, Response], Promise<void>>
  let fetchImpl: Mock<[Request], Promise<Response>>
  let handlers: Record<string, Handler>

  beforeEach(() => {
    enCache = new Map()
    put = vi.fn(async (request: Request, response: Response) => {
      enCache.set(request.url, response)
    })
    const cache = { put, addAll: vi.fn(async () => {}) }
    const caches = {
      open: async () => cache,
      match: async (request: Request) => enCache.get(request.url),
      keys: async () => [],
      delete: vi.fn(),
    }
    fetchImpl = vi.fn(async (_request: Request) => reponse('réseau'))
    handlers = chargerWorker(caches, fetchImpl)
  })

  it('sert la page d’entrée depuis le réseau même quand le cache en a une copie', async () => {
    const page = navigation('https://investai.app/')
    enCache.set(page.url, reponse('ancienne version'))

    const servie = await servir(handlers, page)

    expect(await servie!.text()).toBe('réseau')
  })

  it('retombe sur la copie en cache de la page hors ligne', async () => {
    const page = navigation('https://investai.app/')
    enCache.set(page.url, reponse('ancienne version'))
    fetchImpl.mockRejectedValue(new TypeError('hors ligne'))

    const servie = await servir(handlers, page)

    expect(await servie!.text()).toBe('ancienne version')
  })

  it('sert un fichier haché depuis le cache sans toucher au réseau', async () => {
    const script = new Request('https://investai.app/assets/App-abc123.js')
    enCache.set(script.url, reponse('script en cache'))

    const servie = await servir(handlers, script)

    expect(await servie!.text()).toBe('script en cache')
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('laisse passer les appels d’API sans y toucher', async () => {
    const servie = await servir(handlers, new Request('https://api.investai.app/api/v1/dashboard?days=30'))

    expect(servie).toBeUndefined()
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('ignore les requêtes qui ne sont pas en http', async () => {
    const servie = await servir(handlers, new Request('chrome-extension://abc/script.js'))

    expect(servie).toBeUndefined()
  })

  it('une mise en cache refusée ne rejette rien', async () => {
    put.mockRejectedValue(new TypeError("Failed to execute 'put' on 'Cache'"))
    const rejets: unknown[] = []
    const capter = (raison: unknown) => rejets.push(raison)
    process.on('unhandledRejection', capter)

    const servie = await servir(handlers, new Request('https://investai.app/manifest.json'))
    expect(await servie!.text()).toBe('réseau')
    await new Promise((r) => setTimeout(r, 20))

    process.off('unhandledRejection', capter)
    expect(rejets).toEqual([])
  })
})
