import type { DisplayThresholds } from '@/types'

// ── Core prediction types ────────────────────────────────────────────

export interface PredictionPoint {
  date: string
  price: number
  confidence_low: number
  confidence_high: number
}

export interface PortfolioPrediction {
  symbol: string
  name: string
  asset_type: string
  current_price: number
  predicted_price: number
  change_percent: number
  trend: string
  trend_strength: number
  recommendation: string
  model_used: string
  predictions: PredictionPoint[]
  support_level: number
  resistance_level: number
  skill_score: number
  hit_rate: number
  hit_rate_significant: boolean
  hit_rate_n_samples: number
  reliability_score: number
  model_confidence: string
  models_agree: boolean
  models_detail?: ModelDetail[]
  explanations?: Explanation[]
  regime_info?: RegimeInfo
}

export interface ModelDetail {
  name: string
  weight_pct: number
  trend: string
  mape?: number
}

export interface Explanation {
  feature_name: string
  importance: number
  direction: string
}

export interface RegimeInfo {
  dominant_regime: string
  confidence: number
  probabilities: Record<string, number>
  timeframe_alignment?: string
  weekly_regime?: string | null
  note?: string
  liquidity_warning?: string
  regime_price_adjustment?: boolean
  adjustment_factor?: number
}

export interface PortfolioPredictionSummary {
  total_current_value: number
  total_predicted_value: number
  expected_change_percent: number
  overall_sentiment: string
  bullish_assets: number
  bearish_assets: number
  neutral_assets: number
  days_ahead: number
}

// ── Market types ─────────────────────────────────────────────────────

export interface Anomaly {
  symbol: string
  is_anomaly: boolean
  anomaly_type: string | null
  severity: string
  description: string
  detected_at: string
  price_change_percent: number
}

export interface Signal {
  type: string
  message: string
  action: string
}

export interface MarketSentiment {
  overall_sentiment: string
  sentiment_score: number
  fear_greed_index: number
  market_phase: string
  signals: Signal[]
}

// ── What-If types ────────────────────────────────────────────────────

export interface WhatIfResult {
  current_value: number
  simulated_value: number
  impact_percent: number
  per_asset: WhatIfAsset[]
}

export interface WhatIfAsset {
  symbol: string
  name: string
  current_value: number
  simulated_value: number
  change_percent: number
  impact: number
}

// ── Market Cycle types ───────────────────────────────────────────────

export interface TopBottomEstimate {
  symbol: string
  current_price: number
  next_bottom: {
    estimated_price: number
    estimated_days: number
    estimated_date: string
    confidence: number
    distance_pct: number
    method: string
    support_level: number
  }
  next_top: {
    estimated_price: number
    estimated_days: number
    estimated_date: string
    confidence: number
    distance_pct: number
    method: string
    resistance_level: number
  }
  current_regime: string
  cycle_position: number
  ou_parameters: {
    mu: number
    theta: number
    sigma: number
  }
}

export interface MarketCycleData {
  market_regime: {
    dominant_regime: string
    confidence: number
    probabilities: Record<string, number>
    description: string
  } | null
  market_signals: Array<{
    name: string
    value: number
    signal: string
    strength: number
    description: string
  }>
  portfolio_regime: {
    dominant_regime: string
    probabilities: Record<string, number>
  }
  per_asset: Array<{
    symbol: string
    name: string
    asset_type: string
    value: number
    dominant_regime: string
    confidence: number
    probabilities: Record<string, number>
  }>
  cycle_position: number
  cycle_advice: Array<{
    title: string
    description: string
    action: string
    priority: string
  }>
  fear_greed: number | null
  btc_dominance: number | null
  display_thresholds?: DisplayThresholds
  top_bottom_estimates?: {
    btc: TopBottomEstimate | null
    per_asset: TopBottomEstimate[]
  }
  distribution_diagnostic?: Array<{
    symbol: string
    name: string
    dominant_regime: string
    top_bearish_prob: number
    rsi: number | null
    weight_pct: number
    signals: string[]
    sell_priority: string
  }>
  time_to_pivot?: {
    current_phase: string
    next_phase: string
    estimated_days: number
    confidence: number
    cycle_position: number
  }
}

// ── Backtest types ───────────────────────────────────────────────────

export interface BacktestData {
  per_asset: Array<{
    symbol: string
    mape: number | null
    direction_accuracy: number | null
    points: Array<{ date: string; predicted: number; actual: number }>
  }>
  overall_mape: number | null
  overall_direction_accuracy: number | null
  needs_retraining: boolean
}

// ── Track Record types ───────────────────────────────────────────────

export interface TrackRecordData {
  symbol: string
  records: Array<{
    date: string | null
    target_date: string | null
    predicted_price: number | null
    actual_price: number | null
    mape: number | null
    direction_correct: boolean | null
    ci_covered: boolean | null
  }>
  summary: {
    total_checked: number
    avg_mape: number | null
    direction_accuracy: number | null
    ci_coverage: number | null
  }
}

// ── Chart types ──────────────────────────────────────────────────────

export interface ChartPoint {
  date: string
  price?: number
  confidence_low?: number
  confidence_high?: number
  actual?: number
  predicted_past?: number
  isToday: boolean
}

// ── Unified alert type ───────────────────────────────────────────────

export interface UnifiedAlert {
  symbol?: string
  type: string
  message: string
  severity: 'high' | 'medium' | 'low'
  icon: string
  source: string
}
