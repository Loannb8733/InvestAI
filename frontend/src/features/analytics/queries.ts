import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import { http } from '@/shared/api/http'
import type { AnalysisScope, OptimizeObjective, XirrData } from './types'

export const ANALYTICS_TIMEOUT_MS = 120000
const FIVE_MINUTES = 5 * 60 * 1000
const CACHED = { retry: 1, staleTime: FIVE_MINUTES, refetchOnWindowFocus: false } as const
const KEPT = { placeholderData: keepPreviousData }
const QUIET = { meta: { suppressGlobalError: true } }
const timeout = ANALYTICS_TIMEOUT_MS

const onlyPortfolio = (portfolioId: string | undefined) => (portfolioId ? { portfolio_id: portfolioId } : undefined)

export function useAnalytics({ portfolioId, days }: AnalysisScope) {
  return useQuery({
    queryKey: queryKeys.analytics.global(portfolioId, days),
    queryFn: () =>
      portfolioId
        ? apiClient.get('/analytics/portfolio/{portfolio_id}', { path: { portfolio_id: portfolioId }, query: { days }, timeout })
        : apiClient.get('/analytics', { query: { days }, timeout }),
    ...CACHED,
    ...QUIET,
    ...KEPT,
  })
}

export function useDiversification({ portfolioId, days }: AnalysisScope) {
  return useQuery({
    queryKey: queryKeys.analytics.diversification(portfolioId, days),
    queryFn: () => apiClient.get('/analytics/diversification', { query: { portfolio_id: portfolioId, days }, timeout }),
    ...CACHED,
    ...KEPT,
  })
}

export function useCorrelation({ portfolioId, days }: AnalysisScope) {
  return useQuery({
    queryKey: queryKeys.analytics.correlation(portfolioId, days),
    queryFn: () => apiClient.get('/analytics/correlation', { query: { portfolio_id: portfolioId, days }, timeout }),
    ...CACHED,
    ...KEPT,
  })
}

export function usePerformance(portfolioId: string | undefined, period: string) {
  return useQuery({
    queryKey: queryKeys.analytics.performance(portfolioId, period),
    queryFn: () => apiClient.get('/analytics/performance', { query: { period, portfolio_id: portfolioId }, timeout }),
    ...CACHED,
    ...KEPT,
  })
}

export function useMonteCarlo(portfolioId: string | undefined, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.analytics.monteCarlo(portfolioId, horizon),
    queryFn: () => apiClient.get('/analytics/monte-carlo', { query: { horizon, portfolio_id: portfolioId }, timeout }),
    enabled,
    ...CACHED,
    ...KEPT,
  })
}

export function useXirr(portfolioId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.analytics.xirr(portfolioId),
    queryFn: async () => {
      const response = await http.get<XirrData>('/analytics/xirr', { params: onlyPortfolio(portfolioId) ?? {}, timeout })
      return response.data
    },
    enabled,
    ...CACHED,
  })
}

export function useOptimization(portfolioId: string | undefined, days: number, objective: OptimizeObjective, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.analytics.optimize(portfolioId, days), objective],
    queryFn: () => apiClient.get('/analytics/optimize', { query: { objective, days }, timeout }),
    enabled,
    ...CACHED,
    ...KEPT,
  })
}

export function useStressTest(portfolioId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.analytics.stressTest(portfolioId),
    queryFn: () => apiClient.get('/analytics/stress-test', { query: onlyPortfolio(portfolioId), timeout }),
    enabled,
    ...CACHED,
  })
}

export function useBeta(portfolioId: string | undefined, days: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.analytics.beta(portfolioId, days),
    queryFn: () => apiClient.get('/analytics/beta', { query: { days, portfolio_id: portfolioId }, timeout }),
    enabled,
    ...CACHED,
  })
}

export function useHistoricalValues(days: number) {
  return useQuery({
    queryKey: queryKeys.analytics.historicalData(days),
    queryFn: () => apiClient.get('/dashboard/historical-data', { query: { days } }),
    staleTime: FIVE_MINUTES,
    ...KEPT,
  })
}

export function usePortfolioHealth(days: number) {
  return useQuery({
    queryKey: queryKeys.smartInsights.health(days),
    queryFn: () => apiClient.get('/smart-insights/health', { query: { days }, timeout }),
    staleTime: FIVE_MINUTES,
    ...QUIET,
    ...KEPT,
  })
}
