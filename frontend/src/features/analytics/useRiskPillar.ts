import { useMemo, useState } from 'react'
import { usePortfolioList } from '@/features/portfolio/hooks'
import { usePlanOrder, useRebalance } from './mutations'
import {
  useAnalytics,
  useBeta,
  useCorrelation,
  useDiversification,
  useHistoricalValues,
  useMonteCarlo,
  useOptimization,
  usePerformance,
  usePortfolioHealth,
  useStressTest,
  useXirr,
} from './queries'
import type { OptimizeObjective } from './types'

export const PERIOD_OPTIONS = [
  { value: '7d', label: '7 jours', days: 7 },
  { value: '30d', label: '30 jours', days: 30 },
  { value: '90d', label: '90 jours', days: 90 },
  { value: '1y', label: '1 an', days: 365 },
] as const

const BEAR_REGIMES = ['bearish', 'markdown', 'distribution', 'bottom', 'bottoming']
const BULL_REGIMES = ['bullish', 'markup']
const MIN_WINDOW_DAYS = 30

export function useRiskPillar() {
  const [period, setPeriod] = useState('30d')
  const [portfolio, setPortfolio] = useState('all')
  const [horizon, setHorizon] = useState('90')
  const [objective, setObjective] = useState<OptimizeObjective>('max_sharpe')
  const [plannedSymbols, setPlannedSymbols] = useState<Set<string>>(new Set())

  const days = PERIOD_OPTIONS.find((option) => option.value === period)?.days ?? 30
  const portfolioId = portfolio === 'all' ? undefined : portfolio
  const windowDays = Math.max(MIN_WINDOW_DAYS, days)

  const portfolios = usePortfolioList()
  const analytics = useAnalytics({ portfolioId, days })
  const diversification = useDiversification({ portfolioId, days })
  const correlation = useCorrelation({ portfolioId, days })
  const performance = usePerformance(portfolioId, period)
  const assetCount = analytics.data?.asset_count ?? 0
  const monteCarlo = useMonteCarlo(portfolioId, Number(horizon), assetCount > 0)
  const xirr = useXirr(portfolioId, assetCount > 0)
  const optimization = useOptimization(portfolioId, windowDays, objective, assetCount >= 2)
  const stressTest = useStressTest(portfolioId, assetCount > 0)
  const beta = useBeta(portfolioId, windowDays, assetCount > 0)
  const historical = useHistoricalValues(days)
  const health = usePortfolioHealth(days)
  const rebalance = useRebalance()
  const planOrder = usePlanOrder((symbol) => setPlannedSymbols((previous) => new Set(previous).add(symbol)))

  const regime = health.data?.market_regime?.market?.dominant_regime ?? ''
  const mode = { isBearMode: BEAR_REGIMES.includes(regime), isBullMode: BULL_REGIMES.includes(regime) }

  const evolution = useMemo(
    () =>
      historical.data?.map((point) => ({
        date: point.date,
        fullDate: point.full_date || point.date,
        value: point.value,
        invested: point.invested || 0,
        gain: (point.value || 0) - (point.invested || 0),
      })) || [],
    [historical.data]
  )

  return {
    scope: { period, setPeriod, portfolio, setPortfolio, days, portfolios: portfolios.data },
    horizon,
    setHorizon,
    objective,
    changeObjective: (next: OptimizeObjective) => {
      setObjective(next)
      rebalance.reset()
    },
    plannedSymbols,
    windowDays,
    mode,
    evolution,
    analytics,
    diversification,
    correlation,
    performance,
    monteCarlo,
    xirr,
    optimization,
    stressTest,
    beta,
    health,
    rebalance,
    planOrder,
  }
}

export type RiskPillar = ReturnType<typeof useRiskPillar>
