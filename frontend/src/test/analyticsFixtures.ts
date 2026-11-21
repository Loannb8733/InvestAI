import { ok, type Handler } from './fakeServer'
import { BOURSE, CROWDFUNDING, CRYPTO } from './portfolioFixtures'
import BETA from './analytics/beta.json'
import CORRELATION from './analytics/correlation.json'
import DIVERSIFICATION from './analytics/diversification.json'
import GLOBAL from './analytics/global.json'
import HEALTH from './analytics/health.json'
import HISTORICAL from './analytics/historical.json'
import MONTE_CARLO from './analytics/monteCarlo.json'
import MAX_SHARPE from './analytics/optimizeMaxSharpe.json'
import MIN_VOLATILITY from './analytics/optimizeMinVolatility.json'
import PERFORMANCE from './analytics/performance.json'
import PORTFOLIO from './analytics/portfolio.json'
import REBALANCE from './analytics/rebalance.json'
import STRESS_TEST from './analytics/stressTest.json'
import XIRR from './analytics/xirr.json'

export const NOW = new Date('2026-10-17T14:00:00Z')

const order = (symbol: string, action: string, current_weight: number, target_weight: number, amount_eur: number) => ({
  symbol,
  name: symbol,
  action,
  current_weight,
  target_weight,
  current_value_eur: 62932.455 * current_weight,
  target_value_eur: 62932.455 * target_weight,
  amount_eur,
  reason: `Rapprocher ${symbol} de sa cible MPT`,
})

export const MPT_ORDERS = [
  order('BTC', 'sell', 0.6029, 0.4, -12780.5),
  order('AAPL', 'buy', 0.0637, 0.15, 5431.25),
  order('ETH', 'hold', 0.1562, 0.16, 240),
]

export const HEALTH_WITH_ORDERS = { ...HEALTH, rebalancing_orders: MPT_ORDERS }

export const BEARISH_HEALTH = {
  ...HEALTH_WITH_ORDERS,
  market_regime: { ...HEALTH.market_regime, market: { ...HEALTH.market_regime.market, dominant_regime: 'bearish' } },
}

export const singleAsset = {
  ...GLOBAL,
  asset_count: 1,
  allocation_by_asset: { BTC: 100 },
  allocation_by_type: { crypto: 100 },
  assets: GLOBAL.assets.slice(0, 1).map((asset) => ({ ...asset, weight: 100 })),
}

export const EMPTY_GLOBAL = {
  allocation_by_asset: {},
  allocation_by_type: {},
  asset_count: 0,
  assets: [],
  best_performer: null,
  calmar_ratio: 0,
  concentration_risk: 0,
  cvar_95: 0,
  diversification_score: 0,
  interpretations: {},
  max_drawdown: 0,
  portfolio_volatility: 0,
  sharpe_ratio: 0,
  sortino_ratio: 0,
  total_gain_loss: 0,
  total_gain_loss_percent: 0,
  total_invested: 0,
  total_value: 0,
  var_95: 0,
  var_95_description: '',
  worst_performer: null,
}

export const withGlobalWarning = {
  ...GLOBAL,
  interpretations: { ...GLOBAL.interpretations, global: 'Historique de 12 jours seulement : les ratios sont peu fiables.' },
}

export function analyticsRoutes(): Record<string, Handler> {
  return {
    'GET /portfolios': ok([CRYPTO, BOURSE, CROWDFUNDING]),
    'GET /analytics': ok(GLOBAL),
    'GET /analytics/portfolio/p1': ok(PORTFOLIO),
    'GET /analytics/diversification': ok(DIVERSIFICATION),
    'GET /analytics/correlation': ok(CORRELATION),
    'GET /analytics/performance': ok(PERFORMANCE),
    'GET /analytics/monte-carlo': ok(MONTE_CARLO),
    'GET /analytics/xirr': ok(XIRR),
    'GET /analytics/optimize': (config) => ok(config.params?.objective === 'min_volatility' ? MIN_VOLATILITY : MAX_SHARPE)(config),
    'GET /analytics/stress-test': ok(STRESS_TEST),
    'GET /analytics/beta': ok(BETA),
    'POST /analytics/rebalance': ok(REBALANCE),
    'GET /dashboard/historical-data': ok(HISTORICAL),
    'GET /smart-insights/health': ok(HEALTH_WITH_ORDERS),
    'POST /predictions/planned-orders': (config) => ({
      status: 201,
      data: { id: 'po1', status: 'pending', created_at: '2026-10-17T14:00:00Z', ...JSON.parse(String(config.data)) },
    }),
  }
}
