import type { Schema } from '@/shared/api/client'

export type AnalyticsData = Schema<'PortfolioAnalyticsResponse'>
export type Diversification = Schema<'DiversificationResponse'>
export type Correlation = Schema<'CorrelationResponse'>
export type PerformanceSummary = Schema<'PerformanceSummaryResponse'>
export type MonteCarloData = Schema<'MonteCarloResponse'>
export type StressTestData = Schema<'PortfolioStressTestResponse'>
export type StressScenario = Schema<'StressScenarioResponse'>
export type BetaData = Schema<'BetaResponse'>
export type OptimizeData = Schema<'OptimizationResponse'>
export type RebalanceResponse = Schema<'RebalanceResponse'>
export type PortfolioHealth = Schema<'PortfolioHealthResponse'>
export type RebalancingOrder = Schema<'RebalancingOrderResponse'>
export type AnomalyImpact = Schema<'AnomalyImpactResponse'>
export type MetricsSummary = Schema<'MetricsSummaryResponse'>
export type XirrData = Schema<'XIRRResponse'>

export type OptimizeObjective = 'max_sharpe' | 'min_volatility'

export interface PlanOrderInput {
  symbol: string
  side: 'buy' | 'sell'
  amount_eur: number
}

export interface AnalysisScope {
  portfolioId: string | undefined
  days: number
}
