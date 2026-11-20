import type { InternalAxiosRequestConfig } from 'axios'
import { ok, type Handler } from './fakeServer'

export const NOW = new Date('2026-09-02T12:00:00Z')

const CATALOGUE = [
  ['binance', 'Binance', true, false, "Plus grande plateforme d'échange crypto au monde"],
  ['bitpanda', 'Bitpanda', false, false, "Plateforme d'investissement européenne (crypto, actions, métaux)"],
  ['bitstamp', 'Bitstamp', true, false, "L'un des plus anciens exchanges crypto au monde"],
  ['bybit', 'Bybit', true, false, 'Exchange crypto avec trading de dérivés avancé'],
  ['coinbase', 'Coinbase', true, false, 'Exchange américain grand public avec Advanced Trade'],
  ['cryptocom', 'Crypto.com', true, false, 'Plateforme crypto populaire avec carte Visa et app mobile'],
  ['gateio', 'Gate.io', true, false, "Exchange crypto avec un large choix d'altcoins"],
  ['kraken', 'Kraken', true, false, 'Exchange américain réputé pour sa sécurité'],
  ['kucoin', 'KuCoin', true, true, "Exchange crypto populaire avec large choix d'altcoins"],
  ['okx', 'OKX', true, true, 'Exchange crypto global avec trading spot et dérivés'],
] as const

export const EXCHANGES = CATALOGUE.map(([id, name, requires_secret, requires_passphrase, description]) => ({
  id,
  name,
  requires_secret,
  requires_passphrase,
  description,
}))

const REVOKED =
  "Kraken API error: EAPI:Invalid key. La clé a été révoquée côté plateforme : régénérez une clé en lecture seule puis reconnectez-la depuis cette page."

function apiKey(id: string, exchange: string, extra: object = {}) {
  return {
    id,
    exchange,
    label: null,
    is_active: true,
    status: 'active',
    error_count: 0,
    last_sync_at: null,
    last_error: null,
    created_at: '2026-01-15T09:00:00Z',
    ...extra,
  }
}

export const API_KEYS = [
  apiKey('k1', 'binance', { label: 'Compte principal', last_sync_at: '2026-09-02T10:30:00Z' }),
  apiKey('k2', 'binance', { last_sync_at: '2026-08-31T08:00:00Z', created_at: '2026-03-02T18:45:00Z' }),
  apiKey('k3', 'kraken', {
    label: 'Épargne',
    is_active: false,
    status: 'error',
    error_count: 3,
    last_sync_at: '2026-08-25T08:00:00Z',
    last_error: REVOKED,
  }),
  apiKey('k4', 'okx', { created_at: '2026-08-30T07:00:00Z' }),
]

export const COLD_WALLETS = [
  { id: 'w1', address: 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh', label: 'Ledger', created_at: '2026-02-01T10:00:00Z' },
  { id: 'w2', address: '0x71C7656EC7ab88b098defB751B7401B5f6d8976F', label: 'Tangem', created_at: '2026-02-03T10:00:00Z' },
]

function gap(asset_id: string, symbol: string, exchange: string, missing_qty: number, missing_eur: number, source_hint: string) {
  return { asset_id, symbol, exchange, stored: missing_qty, computed: 0, missing_qty, missing_eur, suggested_action: 'credit_airdrop', source_hint }
}

export const GAPS = [
  gap('a1', 'BNB', 'Binance', 0.2655, 142.37, 'earn_pending'),
  gap('a2', 'ARB', 'Binance', 40, 31.2, 'airdrop'),
  gap('a3', 'DOT', 'Kraken', 0.00000412, 6.05, 'unknown'),
  gap('a4', 'USDC', 'Kraken', 1250, 1150.4, 'earn_pending'),
]

export const gapsFound = ok({ count: GAPS.length, threshold_eur: 5, gaps: GAPS })

export function taskStatus(taskId: string, ...replies: Array<Record<string, unknown>>): Handler {
  let index = 0
  return (config) => {
    const reply = replies[Math.min(index, replies.length - 1)]
    index += 1
    return ok({ task_id: taskId, synced: null, message: null, error: null, ...reply })(config)
  }
}

const body = (config: InternalAxiosRequestConfig) => JSON.parse(String(config.data)) as Record<string, unknown>

export function exchangeRoutes(): Record<string, Handler> {
  return {
    'GET /api-keys/exchanges': ok(EXCHANGES),
    'GET /api-keys': ok(API_KEYS),
    'POST /api-keys': (config) => ({ status: 201, data: apiKey('k9', String(body(config).exchange), { label: body(config).label ?? null }) }),
    'PATCH /api-keys/k1': (config) => ok({ ...API_KEYS[0], ...body(config) })(config),
    'PATCH /api-keys/k3': (config) => ok({ ...API_KEYS[2], ...body(config) })(config),
    'DELETE /api-keys/k2': () => ({ status: 204 }),
    'POST /api-keys/k1/test': ok({
      success: true,
      message: 'Connexion à Binance réussie',
      balance: { BTC: 0.51234567, ETH: 2.5, BNB: 1.5, SHIB: 1520000, PEPE: 0.000004 },
    }),
    'POST /api-keys/k1/sync': ok({ message: 'Synchronisation terminée', synced_assets: 3, portfolio_id: 'p1', portfolio_name: 'Crypto' }),
    'POST /api-keys/k1/import-async': ok({ task_id: 'task-import', status: 'dispatched', message: 'Import lancé' }),
    'POST /api-keys/k1/refresh-fx': ok({ task_id: 'task-fx', status: 'dispatched', message: 'Recalcul lancé' }),
    'GET /api-keys/import-status/task-import': taskStatus('task-import', { status: 'pending' }, { status: 'completed', synced: 12 }),
    'GET /api-keys/import-status/task-fx': taskStatus('task-fx', { status: 'completed', synced: 0 }),
    'GET /transactions/balance-gaps': ok({ count: 0, threshold_eur: 5, gaps: [] }),
    'POST /transactions/balance-gaps/credit-all': ok({ credited: 3, skipped: 1, details: { credited: [], skipped: [] } }),
    'GET /cold-wallets': ok(COLD_WALLETS),
    'POST /cold-wallets': (config) => ({ status: 201, data: { id: 'w9', created_at: '2026-09-02T12:00:00Z', ...body(config) } }),
    'DELETE /cold-wallets/w1': () => ({ status: 204 }),
  }
}
