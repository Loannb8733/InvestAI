import type { InternalAxiosRequestConfig } from 'axios'
import { ok, type Handler } from './fakeServer'

const STAMPS = { user_id: 'u1', created_at: '2026-01-10T08:00:00Z', updated_at: '2026-01-10T08:00:00Z' }

export const CRYPTO = { ...STAMPS, id: 'p1', name: 'Crypto', description: 'Mes cryptos', kind: null, cash_balances: { Binance: 120.5 } }
export const BOURSE = { ...STAMPS, id: 'p2', name: 'Bourse', description: null, kind: null, cash_balances: {} }
export const CROWDFUNDING = { ...STAMPS, id: 'p3', name: 'Mes prêts', description: null, kind: 'crowdfunding', cash_balances: {} }

const position = (fields: Record<string, unknown>) => ({
  name: null,
  asset_type: 'crypto',
  change_percent_24h: 0,
  dividend_income: 0,
  fx_gain: 0,
  first_buy_date: '2025-01-10T12:00:00+00:00',
  ...fields,
})

export const POSITIONS = [
  position({
    id: 'a1', symbol: 'BTC', name: 'Bitcoin', exchange: 'Binance', quantity: 0.5, avg_buy_price: 30000, breakeven_price: 30100,
    current_price: 60000, current_value: 30000, total_invested: 15050, gain_loss: 14950, gain_loss_percent: 99.3355,
    total_fees: 50, risk_weight: 40.5, holding_days: 400, annualized_return: 85.2,
  }),
  position({
    id: 'a2', symbol: 'ETH', exchange: 'Binance', quantity: 2, avg_buy_price: 1500, breakeven_price: 1510,
    current_price: 3000, current_value: 6000, total_invested: 3020, gain_loss: 2980, gain_loss_percent: 98.6755,
    total_fees: 20, risk_weight: 20, holding_days: 200, annualized_return: 50,
  }),
  position({
    id: 'a3', symbol: 'ETH', exchange: 'Kraken', quantity: 1, avg_buy_price: 2000, breakeven_price: 2010,
    current_price: 3000, current_value: 3000, total_invested: 2010, gain_loss: 990, gain_loss_percent: 49.2537,
    total_fees: 10, risk_weight: 20, holding_days: 3, annualized_return: null,
  }),
  position({
    id: 'a4', symbol: 'SOL', exchange: 'Tangem', quantity: 10, avg_buy_price: 150, breakeven_price: 151,
    current_price: 100, current_value: 1000, total_invested: 1510, gain_loss: -510, gain_loss_percent: -33.7748,
    total_fees: 10, risk_weight: 12.25, holding_days: 100, annualized_return: -30.4,
  }),
  position({
    id: 'a5', symbol: 'AAPL', name: 'Apple', asset_type: 'stock', exchange: null, quantity: 3, avg_buy_price: 170,
    breakeven_price: 170, current_price: null, current_value: 510, total_invested: 510, gain_loss: 0, gain_loss_percent: 0,
    total_fees: 0, risk_weight: 0, holding_days: null, annualized_return: null,
  }),
]

export const CRYPTO_METRICS = {
  total_value: 40510,
  total_invested: 22100,
  total_gain_loss: 18410,
  total_gain_loss_percent: 83.3032,
  unrealized_gain: 18410,
  assets: POSITIONS,
  cash_from_stablecoins: 500,
  stablecoins: [
    { id: 's1', symbol: 'USDC', quantity: 540.123, value: 500, unit_price: 0.9257, depeg_percent: 0, depeg_warning: false },
    { id: 's2', symbol: 'USDT', quantity: 0.004, value: 0.0037, unit_price: 0.925, depeg_percent: 0, depeg_warning: false },
  ],
  cash_from_fiat: 200,
  fiat_assets: [{ id: 'f1', symbol: 'EUR', quantity: 200, value: 200, unit_price: 1, depeg_percent: 0, depeg_warning: false }],
}

export const EMPTY_METRICS = {
  total_value: 0,
  total_invested: 0,
  total_gain_loss: 0,
  total_gain_loss_percent: 0,
  assets: [],
  cash_from_stablecoins: 0,
  stablecoins: [],
  cash_from_fiat: 0,
  fiat_assets: [],
}

const sold = (fields: Record<string, unknown>) => ({
  name: null,
  asset_type: 'crypto',
  current_quantity: 0,
  first_transaction: '2025-03-01T12:00:00+00:00',
  last_transaction: '2025-09-15T12:00:00+00:00',
  ...fields,
})

export const CRYPTO_HISTORY = {
  total_invested_all_time: 30000,
  total_sold: 12000,
  total_fees: 95,
  realized_gains: 641,
  current_holdings_count: 5,
  sold_assets_count: 3,
  sold_assets: [
    sold({
      id: 'h3', symbol: 'XRP', exchange: 'Kraken', total_bought: 0.5, total_bought_value: 1000, total_sold: 0.5,
      total_sold_value: 1500, total_fees: 5, realized_gain: 495, first_transaction: '2025-01-05T12:00:00+00:00',
    }),
    sold({
      id: 'h1', symbol: 'ADA', name: 'Cardano', exchange: 'Binance', total_bought: 1000, total_bought_value: 400,
      total_sold: 1000, total_sold_value: 600, total_fees: 2, realized_gain: 198,
    }),
    sold({
      id: 'h2', symbol: 'XRP', exchange: 'Binance', total_bought: 500, total_bought_value: 250, total_sold: 500,
      total_sold_value: 200, total_fees: 2, realized_gain: -52, last_transaction: '2026-02-20T12:00:00+00:00',
    }),
  ],
}

export const EMPTY_HISTORY = {
  total_invested_all_time: 0,
  total_sold: 0,
  total_fees: 0,
  realized_gains: 0,
  current_holdings_count: 0,
  sold_assets_count: 0,
  sold_assets: [],
}

export const SPARKLINES = [
  { symbol: 'BTC', prices: [50000, 55000, 60000], change_pct: 20 },
  { symbol: 'ETH', prices: [3300, 3100, 3000], change_pct: -9.09 },
]

const tx = (fields: Record<string, unknown>) => ({
  fee: 0,
  currency: 'EUR',
  executed_at: '2025-01-10T12:00:00Z',
  created_at: '2025-01-10T12:00:00Z',
  notes: null,
  external_id: null,
  related_transaction_id: null,
  conversion_rate: null,
  ...fields,
})

export const TRANSACTIONS: Record<string, unknown[]> = {
  a1: [
    tx({ id: 't1', asset_id: 'a1', transaction_type: 'buy', quantity: 0.3, price: 28000, fee: 30, exchange: 'Binance' }),
    tx({ id: 't2', asset_id: 'a1', transaction_type: 'buy', quantity: 0.2, price: 33000, fee: 20, exchange: 'Binance', executed_at: null, created_at: '2025-06-01T12:00:00Z' }),
  ],
  a2: [tx({ id: 't3', asset_id: 'a2', transaction_type: 'buy', quantity: 2, price: 1500, fee: 20, exchange: 'Binance', executed_at: '2025-07-01T12:00:00Z' })],
  a3: [tx({ id: 't4', asset_id: 'a3', transaction_type: 'transfer_in', quantity: 1, price: 2000, exchange: 'Kraken', executed_at: '2026-03-01T12:00:00Z' })],
}

const body = (config: InternalAxiosRequestConfig) => JSON.parse(String(config.data)) as Record<string, unknown>
const noContent: Handler = () => ({ status: 204 })

export function portfolioRoutes(): Record<string, Handler> {
  return {
    'GET /portfolios': ok([CRYPTO, BOURSE, CROWDFUNDING]),
    'POST /portfolios': (config) => ({ status: 201, data: { ...STAMPS, id: 'p9', kind: null, cash_balances: {}, description: null, ...body(config) } }),
    'DELETE /portfolios/p1': noContent,
    'DELETE /portfolios/p2': noContent,
    'PUT /portfolios/p1/cash-balance': (config) => {
      const { exchange, amount } = body(config) as { exchange: string; amount: number }
      return { status: 200, data: { ...CRYPTO, cash_balances: { ...CRYPTO.cash_balances, [exchange]: amount } } }
    },
    'DELETE /portfolios/p1/cash-balance/Binance': ok({ ...CRYPTO, cash_balances: {} }),
    'GET /dashboard/portfolio/p1': ok(CRYPTO_METRICS),
    'GET /dashboard/portfolio/p2': ok(EMPTY_METRICS),
    'GET /dashboard/portfolio/p1/sparklines': ok(SPARKLINES),
    'GET /dashboard/portfolio/p2/sparklines': ok([]),
    'GET /dashboard/portfolio/p1/history': ok(CRYPTO_HISTORY),
    'GET /dashboard/portfolio/p2/history': ok(EMPTY_HISTORY),
    'GET /transactions': (config) => ok(TRANSACTIONS[(config.params as { asset_id: string }).asset_id] ?? [])(config),
    'GET /transactions/platforms': ok({ platforms: ['Binance', 'Kraken', 'Boursorama'] }),
    'GET /transactions/csv-platforms': ok({ platforms: [] }),
    'POST /assets': (config) => ({ status: 201, data: { ...STAMPS, id: 'a9', currency: 'EUR', exchange: null, ...body(config) } }),
    'PATCH /assets/a1': (config) => ({ status: 200, data: { ...POSITIONS[0], ...body(config) } }),
    'PATCH /assets/a3': (config) => ({ status: 200, data: { ...POSITIONS[2], ...body(config) } }),
    'DELETE /assets/a1': noContent,
    'DELETE /assets/a4': noContent,
  }
}
