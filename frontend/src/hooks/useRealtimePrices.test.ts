import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { pricesSocketUrl } from './useRealtimePrices'

afterEach(() => {
  vi.unstubAllEnvs()
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
