import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { pricesSocketUrl, useRealtimePrices } from './useRealtimePrices'

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selecteur: (e: unknown) => unknown) => selecteur({ accessToken: 'jeton' }),
}))
vi.mock('@/hooks/usePageVisibility', () => ({ usePageVisibility: () => true }))

class FauxSocket {
  static readonly OPEN = 1
  static dernier: FauxSocket
  readonly readyState = FauxSocket.OPEN
  envoyes: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor() {
    FauxSocket.dernier = this
  }

  send(message: string) {
    this.envoyes.push(JSON.parse(message))
  }

  close() {}

  recevoir(message: unknown) {
    act(() => this.onmessage?.({ data: JSON.stringify(message) }))
  }
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('pricesSocketUrl', () => {
  it("vise l'API directement quand VITE_WS_URL est défini, même si le HTTP passe par le proxy", () => {
    vi.stubEnv('VITE_API_URL', '/api/v1')
    vi.stubEnv('VITE_WS_URL', 'wss://api.test/api/v1')
    expect(pricesSocketUrl()).toBe('wss://api.test/api/v1/ws/prices')
  })

  it("dérive l'URL d'une API absolue sans VITE_WS_URL", () => {
    vi.stubEnv('VITE_API_URL', 'http://localhost:8000/api/v1')
    vi.stubEnv('VITE_WS_URL', '')
    expect(pricesSocketUrl()).toBe('ws://localhost:8000/api/v1/ws/prices')
  })

  it("reste sur l'hôte courant avec une API relative", () => {
    vi.stubEnv('VITE_API_URL', '/api/v1')
    vi.stubEnv('VITE_WS_URL', '')
    expect(pricesSocketUrl()).toBe(`ws://${window.location.host}/api/v1/ws/prices`)
  })
})

describe('useRealtimePrices', () => {
  it('demande les cours dans la devise voulue et ne garde que ceux-là', () => {
    vi.stubGlobal('WebSocket', FauxSocket)
    const { result } = renderHook(() => useRealtimePrices(['BTC'], 'USD'))
    const socket = FauxSocket.dernier
    act(() => socket.onopen?.())
    socket.recevoir({ type: 'auth', status: 'ok' })

    expect(socket.envoyes).toEqual([
      { action: 'auth', token: 'jeton' },
      { action: 'subscribe', symbols: ['BTC'], currency: 'USD' },
    ])

    socket.recevoir({ type: 'price', symbol: 'BTC', price: 90, change_24h_percent: 1, currency: 'EUR' })
    expect(result.current.prices).toEqual({})

    socket.recevoir({ type: 'price', symbol: 'BTC', price: 100, change_24h_percent: 1, currency: 'USD' })
    expect(result.current.prices.BTC?.price).toBe(100)
  })
})

describe('déploiement Vercel', () => {
  const vercel = JSON.parse(readFileSync(resolve(process.cwd(), '../vercel.json'), 'utf-8'))

  it("garde l'API sur l'origine du site : un cookie inter-sites est bloqué par les navigateurs", () => {
    expect(vercel.buildCommand).toContain('VITE_API_URL=/api/v1 ')
    expect(vercel.rewrites[0].source).toBe('/api/v1/:path*')
  })

  it('garde le websocket en direct : les réécritures Vercel ne le relaient pas', () => {
    expect(vercel.buildCommand).toMatch(/VITE_WS_URL=wss:\/\/\S+\/api\/v1 /)
  })
})
