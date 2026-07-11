/**
 * Types du pilier « Risque & Performance » (hub Intelligence).
 *
 * Copiés depuis AnalyticsPage.tsx et SmartInsightsPage.tsx pendant la phase
 * de coexistence : les anciennes pages restent intactes, le pilier ne les
 * importe pas. Les formes sont structurellement identiques aux réponses API,
 * donc le cache React Query est partagé (mêmes query keys).
 */

// ── Analytics (source : AnalyticsPage) ────────────────────────────────

export interface AnalyticsData {
  total_value: number
  total_invested: number
  total_gain_loss: number
  total_gain_loss_percent: number
  portfolio_volatility: number
  sharpe_ratio: number
  sortino_ratio: number
  calmar_ratio: number
  max_drawdown: number
  var_95: number
  cvar_95: number
  var_95_description?: string
  diversification_score: number
  concentration_risk: number
  asset_count: number
  allocation_by_type: Record<string, number>
  allocation_by_asset: Record<string, number>
  assets: Array<{
    symbol: string
    name: string
    asset_type: string
    current_value: number
    gain_loss_percent: number
    weight: number
    volatility_30d: number
    sharpe_ratio: number
    sortino_ratio: number
    max_drawdown: number
    daily_return: number
  }>
  best_performer: string | null
  worst_performer: string | null
  interpretations?: Record<string, string>
}

export interface Diversification {
  score: number
  concentration_risk: number
  asset_count: number
  type_count: number
  allocation_by_type: Record<string, number>
  recommendations: Array<{
    type: string
    severity: string
    message: string
    action: string
  }>
  rating: string
}

export interface Correlation {
  symbols: string[]
  matrix: number[][]
  strongly_correlated: [string, string, number][]
  negatively_correlated: [string, string, number][]
}

export interface PerformanceItem {
  symbol: string
  name: string
  asset_type: string
  gain_loss_percent: number
}

export interface PerformanceSummary {
  top_gainers: PerformanceItem[]
  top_losers: PerformanceItem[]
}

export interface HistoricalDataPoint {
  date: string
  full_date?: string
  value: number
  invested?: number
  gain_loss?: number
}

export interface MonteCarloData {
  percentiles: Record<string, number>
  expected_return: number
  prob_positive: number
  prob_loss_10: number
  prob_ruin: number
  simulations: number
  horizon_days: number
}

export interface StressScenario {
  id: string
  name: string
  description: string
  duration_days: number
  stressed_value: number
  total_loss: number
  total_loss_pct: number
  estimated_recovery_months: number
  per_asset: Array<{
    symbol: string
    name: string
    current_value: number
    stressed_value: number
    loss: number
    shock_pct: number
    risk_weight: number
  }>
}

export interface StressTestData {
  total_value: number
  currency: string
  scenarios: StressScenario[]
  max_drawdown: {
    value: number
    scenario: string
    estimated_recovery_months: number
  } | null
}

export interface BetaAsset {
  symbol: string
  asset_type: string
  beta: number | null
  benchmark: string
  interpretation: string
  value: number
}

export interface BetaData {
  assets: BetaAsset[]
  portfolio_beta_crypto: number | null
  portfolio_beta_stock: number | null
  benchmarks: Record<string, string>
}

export interface OptimizeData {
  weights: Record<string, number>
  expected_return: number
  expected_volatility: number
  sharpe_ratio: number
}

export interface RebalanceOrder {
  symbol: string
  name: string
  asset_type: string
  current_weight: number
  target_weight: number
  diff_weight: number
  current_value: number
  target_value: number
  diff_value: number
  action: string
}

export interface RebalanceResponse {
  orders: RebalanceOrder[]
}

export type OptimizeObjective = 'max_sharpe' | 'min_volatility'

// ── Smart Insights (source : SmartInsightsPage) ───────────────────────

export interface Insight {
  category: string
  severity: string
  title: string
  message: string
  metric_name?: string
  current_value?: number
  target_value?: number
  potential_improvement?: string
  actions: Array<{
    type: string
    symbol: string
    amount_eur?: number
    reason?: string
  }>
}

export interface RebalancingOrder {
  symbol: string
  name: string
  action: string
  current_weight: number
  target_weight: number
  current_value_eur: number
  target_value_eur: number
  amount_eur: number
  reason: string
}

export interface AnomalyImpact {
  symbol: string
  anomaly_type: string
  severity: string
  description: string
  price_change_percent: number
  position_value_eur: number
  impact_eur: number
  detected_at: string
}

export interface RegimeConfig {
  risk_multiplier: number
  alpha_threshold: number
  gold_relevance: string
  mode_label: string
  vol_regime: string
}

export interface MetricsSummary {
  sharpe_ratio: number
  sortino_ratio: number
  volatility: number
  var_95: number
  var_95_window?: number
  max_drawdown: number
  hhi: number
  total_value: number
  days?: number
  gold_exposure?: number
  gold_beta?: number | null
  gold_badge?: string | null
  regime_config?: RegimeConfig | null
  avg_top5_correlation?: number | null
  risk_clusters?: Array<{ assets: string[]; avg_corr: number }> | null
}

export interface IndicatorSignal {
  name: string
  value: number
  signal: string
  strength: number
  description: string
}

export interface RegimeResult {
  symbol: string
  probabilities: Record<string, number>
  dominant_regime: string
  confidence: number
  signals: IndicatorSignal[]
  description: string
}

export interface MarketRegime {
  market: RegimeResult
  per_asset: RegimeResult[]
  generated_at: string
}

export interface PortfolioHealth {
  overall_score: number
  overall_status: string
  insights: Insight[]
  rebalancing_orders: RebalancingOrder[]
  anomaly_impacts: AnomalyImpact[]
  metrics_summary: MetricsSummary
  market_regime?: MarketRegime | null
  generated_at: string
}

/** Entrée du pont « Planifier » (rebalancing MPT → ordres planifiés). */
export interface PlanOrderInput {
  symbol: string
  side: 'buy' | 'sell'
  amount_eur: number
}
