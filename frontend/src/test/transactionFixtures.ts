import type { InternalAxiosRequestConfig } from 'axios'
import { ok, type Handler } from './fakeServer'
import { BOURSE, CROWDFUNDING, CRYPTO } from './portfolioFixtures'

type Tx = Record<string, unknown> & { id: string; asset_id: string; transaction_type: string; exchange: string | null }

const ASSETS = {
  a1: { symbol: 'BTC', name: 'Bitcoin', asset_type: 'crypto', portfolio_id: 'p1', exchange: 'Binance', quantity: 0.5 },
  a2: { symbol: 'ETH', name: 'Ethereum', asset_type: 'crypto', portfolio_id: 'p1', exchange: 'Binance', quantity: 2 },
  a3: { symbol: 'ETH', name: 'Ethereum', asset_type: 'crypto', portfolio_id: 'p1', exchange: 'Kraken', quantity: 1 },
  a4: { symbol: 'SOL', name: 'Solana', asset_type: 'crypto', portfolio_id: 'p1', exchange: 'Tangem', quantity: 10 },
  a5: { symbol: 'AAPL', name: 'Apple', asset_type: 'stock', portfolio_id: 'p2', exchange: null, quantity: 3 },
} as const

type AssetId = keyof typeof ASSETS

export const ASSET_LIST = Object.entries(ASSETS).map(([id, asset]) => ({
  id,
  ...asset,
  avg_buy_price: 100,
  currency: 'EUR',
  current_price: null,
  interest_rate: null,
  maturity_date: null,
  project_status: null,
  invested_amount: null,
  user_id: 'u1',
  created_at: '2025-01-01T08:00:00Z',
  updated_at: '2025-01-01T08:00:00Z',
}))

function tx(id: string, asset: AssetId, type: string, quantity: number, price: number, executedAt: string | null, extra: object = {}): Tx {
  const { symbol, name, asset_type, exchange } = ASSETS[asset]
  return {
    id,
    asset_id: asset,
    transaction_type: type,
    quantity,
    price,
    fee: 0,
    fee_currency: null,
    currency: 'EUR',
    executed_at: executedAt,
    notes: null,
    exchange,
    external_id: null,
    created_at: executedAt ?? '2025-02-02T09:15:00Z',
    asset_symbol: symbol,
    asset_name: name,
    asset_type,
    ...extra,
  }
}

const dca = Array.from({ length: 16 }, (_, i) => {
  const month = String((i % 12) + 1).padStart(2, '0')
  const year = 2025 + Math.floor(i / 12)
  return tx(`dca${i + 1}`, 'a1', 'buy', 0.01, 40000 + i * 1000, `${year}-${month}-05T08:30:00Z`, { fee: 1.5 })
})

export const TRANSACTIONS: Tx[] = [
  ...dca,
  tx('t1', 'a2', 'buy', 2, 1500, '2025-03-10T14:00:00Z', { fee: 4, notes: 'Achat; long terme' }),
  tx('t2', 'a2', 'sell', 0.5, 3200, '2026-02-20T16:45:00Z', { fee: 2.5 }),
  tx('t3', 'a3', 'transfer_in', 1, 0, '2025-06-01T10:00:00Z'),
  tx('t4', 'a4', 'transfer_in', 10, 140, '2025-07-12T11:20:00Z'),
  tx('t5', 'a4', 'staking_reward', 0.0042, 150, '2026-03-01T00:00:00Z'),
  tx('t6', 'a5', 'buy', 3, 175.25, '2025-09-15T15:30:00Z', { fee: 1, currency: 'USD' }),
  tx('t7', 'a1', 'conversion_out', 0.002, 52000, null, { exchange: null }),
]

const dateOf = (t: Tx) => String(t.executed_at ?? t.created_at)
const byDateDesc = (a: Tx, b: Tx) => dateOf(b).localeCompare(dateOf(a))

type ListParams = Partial<Record<'portfolio_id' | 'transaction_type' | 'exchange' | 'asset_symbol' | 'search', string>> & {
  skip?: number
  limit?: number
  include_total?: boolean
}

function matches(t: Tx, p: ListParams) {
  const type = p.transaction_type
  const sameType = !type || (type === 'conversions' ? t.transaction_type.startsWith('conversion') : t.transaction_type === type)
  const portfolio = ASSETS[t.asset_id as AssetId].portfolio_id
  const sameExchange = !p.exchange || (p.exchange === 'Manuel' ? !t.exchange : t.exchange?.toLowerCase() === p.exchange.toLowerCase())
  const text = `${t.asset_symbol} ${t.notes ?? ''}`.toLowerCase()
  return (
    sameType &&
    sameExchange &&
    (!p.portfolio_id || portfolio === p.portfolio_id) &&
    (!p.asset_symbol || t.asset_symbol === p.asset_symbol) &&
    (!p.search || text.includes(p.search.toLowerCase()))
  )
}

export function listTransactions(all: Tx[], extraTotal = 0): Handler {
  return (config: InternalAxiosRequestConfig) => {
    const params = (config.params ?? {}) as ListParams
    const rows = all.filter((t) => matches(t, params)).sort(byDateDesc)
    const page = rows.slice(params.skip ?? 0, (params.skip ?? 0) + (params.limit ?? 100))
    return ok(params.include_total ? { items: page, total: rows.length + extraTotal } : page)(config)
  }
}

const body = (config: InternalAxiosRequestConfig) => JSON.parse(String(config.data)) as Record<string, unknown>

export function transactionRoutes(): Record<string, Handler> {
  return {
    'GET /portfolios': ok([CRYPTO, BOURSE, CROWDFUNDING]),
    'GET /assets': ok(ASSET_LIST),
    'GET /transactions': listTransactions(TRANSACTIONS),
    'GET /transactions/platforms': ok({ platforms: ['Binance', 'Kraken', 'Boursorama'] }),
    'GET /transactions/csv-platforms': ok({ platforms: ['Binance', 'Kraken', 'Crypto.com', 'OKX'] }),
    'GET /transactions/export-csv': ok('symbol;type\n'),
    'POST /transactions': (config) => ({
      status: 201,
      data: { ...TRANSACTIONS[0], id: 't9', ...body(config), created_at: '2026-11-17T10:00:00Z' },
    }),
    'PATCH /transactions/t1': (config) => ({ status: 200, data: { ...TRANSACTIONS[16], ...body(config) } }),
    'DELETE /transactions/t2': () => ({ status: 204 }),
    'DELETE /transactions/dca16': () => ({ status: 204 }),
    'DELETE /transactions/dca15': () => ({ status: 204 }),
    'DELETE /transactions/all': ok({ deleted_count: 23 }),
    'POST /transactions/import-csv': ok({ success_count: 3, error_count: 0, skipped_count: 0, errors: [], created_transactions: ['n1', 'n2', 'n3'] }),
    'POST /assets': (config) => ({ status: 201, data: { ...ASSET_LIST[0], id: 'a9', ...body(config) } }),
  }
}
