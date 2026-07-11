import { useMemo, useState } from 'react'
import { useQuery, useMutation, keepPreviousData } from '@tanstack/react-query'
import type { PortfolioSummary as Portfolio } from '@/types'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import EmptyState from '@/components/ui/empty-state'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import { analyticsApi, dashboardApi, portfoliosApi, predictionsApi, smartInsightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/hooks/use-toast'
import {
  Activity,
  BarChart3,
  FileSpreadsheet,
  Info,
  RefreshCw,
} from 'lucide-react'
import PortfolioEvolutionChart from '@/components/analytics/PortfolioEvolutionChart'
import MonteCarloCard from '@/components/analytics/MonteCarloCard'
import StressTestCard from '@/components/analytics/StressTestCard'
import CorrelationMatrix from '@/components/analytics/CorrelationMatrix'
import HealthScoreSection from './risk/HealthScoreSection'
import RiskMetricRows from './risk/RiskMetricRows'
import SmartRiskCards from './risk/SmartRiskCards'
import OptimizationSection from './risk/OptimizationSection'
import AllocationRiskCharts from './risk/AllocationRiskCharts'
import PerformanceCharts from './risk/PerformanceCharts'
import { BetaCard, DiversificationRecommendations, TopWorstPerformers } from './risk/AnalyticsExtras'
import type {
  AnalyticsData,
  BetaData,
  Correlation,
  Diversification,
  HistoricalDataPoint,
  MonteCarloData,
  OptimizeData,
  OptimizeObjective,
  PerformanceSummary,
  PlanOrderInput,
  PortfolioHealth,
  RebalanceResponse,
  StressTestData,
} from './risk/types'

/**
 * Pilier « Risque & Performance » du hub Intelligence.
 *
 * Fusion réelle d'AnalyticsPage + SmartInsightsPage :
 * - UN sélecteur période/portefeuille pilote TOUTES les queries du pilier
 *   (Analytics ET Smart Insights) — fini le Sharpe différent entre 2 onglets ;
 * - les métriques de risque viennent UNIQUEMENT des queries Analytics
 *   (les cartes dupliquées de SmartInsights sont supprimées) ;
 * - les différenciateurs SmartInsights sont conservés (score de santé,
 *   Risk Clusters, exposition Or, Flash Crash, Recommandations IA, MPT) ;
 * - AUCUNE bannière/carte de régime : le régime vit dans RegimeHeader.tsx,
 *   partagé par le hub.
 *
 * Rendu DANS le hub : pas de <h1>, pas de Breadcrumb. Les query keys des
 * anciennes pages sont conservées à l'identique (cache partagé pendant la
 * coexistence, pas de double fetch).
 */

// Période d'analyse unique : intersection des sélecteurs Analytics (7/30/90j/1an)
// et SmartInsights (7/30/90/365j) — le endpoint santé n'accepte que ces fenêtres.
const PERIOD_OPTIONS = [
  { value: '7d', label: '7 jours', days: 7 },
  { value: '30d', label: '30 jours', days: 30 },
  { value: '90d', label: '90 jours', days: 90 },
  { value: '1y', label: '1 an', days: 365 },
] as const

const safeFixed = (v: number | null | undefined, d: number): string =>
  v == null || isNaN(v) ? '—' : v.toFixed(d)

export default function RiskPerformancePillar() {
  const { toast } = useToast()
  // Sélecteur UNIQUE : période + portefeuille — pilotent tout le pilier.
  const [period, setPeriod] = useState('30d')
  const [selectedPortfolio, setSelectedPortfolio] = useState<string>('all')
  // Horizon de projection Monte Carlo — volontairement découplé de la période
  // d'analyse (le lookback n'est pas un horizon de projection).
  const [mcHorizon, setMcHorizon] = useState('90')
  // Objectif d'optimisation Markowitz
  const [optimizeObjective, setOptimizeObjective] = useState<OptimizeObjective>('max_sharpe')
  // Ordres MPT déjà planifiés (pont Smart Insights → Signaux Alpha)
  const [plannedSymbols, setPlannedSymbols] = useState<Set<string>>(new Set())

  const periodDays = PERIOD_OPTIONS.find((o) => o.value === period)?.days ?? 30
  const portfolioParam = selectedPortfolio === 'all' ? undefined : selectedPortfolio

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: queryKeys.portfolios.list(),
    queryFn: portfoliosApi.list,
    staleTime: 60_000,
  })

  const analyticsQueryOpts = { retry: 1, staleTime: 5 * 60 * 1000, refetchOnWindowFocus: false } as const

  // ── Queries Analytics (source unique des métriques de risque) ──
  const { data: analytics, isLoading: loadingAnalytics, isError: errorAnalytics } = useQuery<AnalyticsData>({
    queryKey: queryKeys.analytics.global(portfolioParam, periodDays),
    queryFn: () => selectedPortfolio === 'all'
      ? analyticsApi.getGlobal(periodDays)
      : analyticsApi.getPortfolio(selectedPortfolio, periodDays),
    ...analyticsQueryOpts,
    // Le pilier affiche sa propre carte d'erreur → pas de toast global (pas de double signalement).
    meta: { suppressGlobalError: true },
    placeholderData: keepPreviousData,
  })

  const { data: diversification, isLoading: loadingDiversification } = useQuery<Diversification>({
    queryKey: queryKeys.analytics.diversification(portfolioParam, periodDays),
    queryFn: () => analyticsApi.getDiversification(portfolioParam, periodDays),
    ...analyticsQueryOpts,
    placeholderData: keepPreviousData,
  })

  const { data: correlation } = useQuery<Correlation>({
    queryKey: queryKeys.analytics.correlation(portfolioParam, periodDays),
    queryFn: () => analyticsApi.getCorrelation(portfolioParam, periodDays),
    ...analyticsQueryOpts,
    placeholderData: keepPreviousData,
  })

  const { data: performance } = useQuery<PerformanceSummary>({
    queryKey: queryKeys.analytics.performance(portfolioParam, period),
    queryFn: () => analyticsApi.getPerformance(period, portfolioParam),
    ...analyticsQueryOpts,
    placeholderData: keepPreviousData,
  })

  const monteCarloHorizon = Number(mcHorizon)
  const { data: monteCarlo } = useQuery<MonteCarloData>({
    queryKey: queryKeys.analytics.monteCarlo(portfolioParam, monteCarloHorizon),
    queryFn: () => analyticsApi.getMonteCarlo(monteCarloHorizon, portfolioParam),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
    placeholderData: keepPreviousData,
  })

  const { data: xirrData } = useQuery<{ xirr: number | null }>({
    queryKey: queryKeys.analytics.xirr(portfolioParam),
    queryFn: () => analyticsApi.getXirr(portfolioParam ?? undefined),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const optimizeDays = Math.max(30, periodDays || 90)
  const { data: optimization } = useQuery<OptimizeData>({
    queryKey: [...queryKeys.analytics.optimize(portfolioParam, optimizeDays), optimizeObjective],
    queryFn: () => analyticsApi.getOptimize(optimizeObjective, optimizeDays),
    enabled: !!analytics && analytics.asset_count >= 2,
    ...analyticsQueryOpts,
    placeholderData: keepPreviousData,
  })

  const { data: stressTest } = useQuery<StressTestData>({
    queryKey: queryKeys.analytics.stressTest(portfolioParam),
    queryFn: () => analyticsApi.getStressTest(portfolioParam),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const betaDays = Math.max(30, periodDays || 365)
  const { data: betaData } = useQuery<BetaData>({
    queryKey: queryKeys.analytics.beta(portfolioParam, betaDays),
    queryFn: () => analyticsApi.getBeta(betaDays, portfolioParam),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const { data: historicalData } = useQuery<HistoricalDataPoint[]>({
    queryKey: queryKeys.analytics.historicalData(periodDays),
    queryFn: () => dashboardApi.getHistoricalData(periodDays),
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  })

  // ── Query Smart Insights (score de santé + différenciateurs) ──
  // Même période que le reste du pilier : le score et les métriques Analytics
  // parlent enfin de la même fenêtre.
  const {
    data: health,
    isLoading: loadingHealth,
    isError: errorHealth,
    refetch: refetchHealth,
    isFetching: fetchingHealth,
  } = useQuery<PortfolioHealth>({
    queryKey: queryKeys.smartInsights.health(periodDays),
    meta: { suppressGlobalError: true },
    queryFn: () => smartInsightsApi.getHealth(periodDays),
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  })

  // ── Mutations ──
  // Ordres de rééquilibrage vers l'allocation optimale (Markowitz)
  const rebalanceMutation = useMutation<RebalanceResponse, Error, Record<string, number>>({
    mutationFn: (targetWeights) => analyticsApi.postRebalance(targetWeights),
  })

  // Pont rebalancing MPT → ordres planifiés (Signaux Alpha)
  const planOrderMutation = useMutation<unknown, Error, PlanOrderInput>({
    mutationFn: (order) =>
      predictionsApi.createPlannedOrder({
        ...order,
        notes: 'Rééquilibrage MPT (Smart Insights)',
        source: 'frontend',
      }),
    onSuccess: (_data, order) => {
      setPlannedSymbols((prev) => new Set(prev).add(order.symbol))
      toast({ title: 'Ordre planifié', description: `${order.symbol} — visible dans Signaux Alpha.` })
    },
    onError: () => toast({ title: "Impossible de planifier l'ordre", variant: 'destructive' }),
  })

  // Modes régime : utilisés uniquement pour adapter les libellés d'action
  // (Accumuler / Prendre profits). Aucune bannière/carte de régime ici —
  // l'affichage du régime appartient à RegimeHeader (partagé par le hub).
  const dominantRegime = health?.market_regime?.market?.dominant_regime ?? ''
  const isBearMode = ['bearish', 'markdown', 'distribution', 'bottom', 'bottoming'].includes(dominantRegime)
  const isBullMode = ['bullish', 'markup'].includes(dominantRegime)

  const chartHistoricalData = useMemo(
    () =>
      historicalData?.map((point) => ({
        date: point.date,
        fullDate: point.full_date || point.date,
        value: point.value,
        invested: point.invested || 0,
        gain: (point.value || 0) - (point.invested || 0),
      })) || [],
    [historicalData]
  )

  if (loadingAnalytics || loadingDiversification) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
      </div>
    )
  }

  if (errorAnalytics) {
    return (
      <EmptyState
        variant="error"
        icon={Activity}
        title="Erreur de chargement"
        description="Impossible de charger les analyses de risque. Veuillez réessayer."
      />
    )
  }

  if (!analytics || analytics.asset_count === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Aucune donnée à analyser"
        description="Ajoutez des actifs à vos portefeuilles pour voir le risque et la performance."
      />
    )
  }

  const exportToCSV = () => {
    const escapeCSV = (val: string) => {
      if (val.includes(',') || val.includes('"') || val.includes('\n')) {
        return `"${val.replace(/"/g, '""')}"`
      }
      return val
    }

    const headers = ['Actif', 'Type', 'Valeur (EUR)', 'Performance %', 'Poids %', 'Volatilité', 'Sharpe', 'Sortino', 'Max Drawdown', 'Rendement J']
    const rows = analytics.assets.map(a => [
      escapeCSV(a.symbol),
      escapeCSV(a.asset_type),
      safeFixed(a.current_value, 2),
      safeFixed(a.gain_loss_percent, 2),
      safeFixed(a.weight, 2),
      safeFixed(a.volatility_30d, 2),
      safeFixed(a.sharpe_ratio, 2),
      safeFixed(a.sortino_ratio, 2),
      safeFixed(a.max_drawdown, 2),
      safeFixed(a.daily_return, 2),
    ])

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const bom = '\uFEFF'
    const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `analyse-portefeuille-${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* 1. Sélecteur UNIQUE : pilote toutes les métriques du pilier */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Période et portefeuille communs à tout le pilier — score, métriques et
          optimisations parlent de la même fenêtre.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={selectedPortfolio} onValueChange={setSelectedPortfolio}>
            <SelectTrigger className="w-40" aria-label="Portefeuille analysé">
              <SelectValue placeholder="Portefeuille" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les portefeuilles</SelectItem>
              {portfolios?.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-28" aria-label="Période d'analyse">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={exportToCSV}>
            <FileSpreadsheet className="h-4 w-4 mr-1" />
            CSV
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetchHealth()}
            disabled={fetchingHealth}
            aria-label="Actualiser le score de santé"
          >
            <RefreshCw className={`h-4 w-4 ${fetchingHealth ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* 2. Score de santé décomposé (Smart Insights) — en tête de pilier */}
      <HealthScoreSection
        health={health}
        isLoading={loadingHealth}
        isError={errorHealth}
        onRetry={() => refetchHealth()}
        days={periodDays}
        isBearMode={isBearMode}
        isBullMode={isBullMode}
      />

      {/* Avertissement historique court (interprétation backend) */}
      {analytics.interpretations?.global && (
        <div className="flex items-center gap-2 rounded-lg border border-warning dark:border-warning bg-warning dark:bg-warning/20 p-3">
          <Info className="h-4 w-4 text-warning flex-shrink-0" />
          <p className="text-sm text-warning dark:text-warning">{analytics.interpretations.global}</p>
        </div>
      )}

      {/* 3. Métriques de risque UNIFIÉES (queries Analytics uniquement) */}
      <RiskMetricRows
        analytics={analytics}
        diversification={diversification}
        xirr={xirrData?.xirr}
      />

      {/* 4. Différenciateurs Smart Insights (clusters, or, flash crash) */}
      {health && (
        <SmartRiskCards
          metrics={health.metrics_summary}
          anomalyImpacts={health.anomaly_impacts}
        />
      )}

      {/* 5. Optimisation & rééquilibrage : les deux moteurs côte à côte */}
      <OptimizationSection
        optimization={optimization}
        allocationByAsset={analytics.allocation_by_asset}
        assetCount={analytics.asset_count}
        optimizeObjective={optimizeObjective}
        onObjectiveChange={(objective) => {
          setOptimizeObjective(objective)
          rebalanceMutation.reset()
        }}
        rebalanceMutation={rebalanceMutation}
        mptOrders={health?.rebalancing_orders ?? []}
        plannedSymbols={plannedSymbols}
        onPlanOrder={(order) => planOrderMutation.mutate(order)}
        isPlanningOrder={planOrderMutation.isPending}
        isBearMode={isBearMode}
        isBullMode={isBullMode}
      />

      {/* 6. Le reste d'Analytics — évolution, radar, Monte Carlo, stress,
          beta, corrélations, top-10, performance par période */}
      <PortfolioEvolutionChart chartHistoricalData={chartHistoricalData} />

      <AllocationRiskCharts
        analytics={analytics}
        diversificationScore={diversification?.score || 0}
      />

      {/* Monte Carlo (horizon découplé) + Stress test */}
      {((monteCarlo && monteCarlo.simulations > 0) || (stressTest && stressTest.scenarios.length > 0)) && (
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          {monteCarlo && monteCarlo.simulations > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-end gap-2">
                <span className="text-xs text-muted-foreground">Horizon de projection</span>
                <Select value={mcHorizon} onValueChange={setMcHorizon}>
                  <SelectTrigger className="h-8 w-28" aria-label="Horizon de projection Monte Carlo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="30">30 jours</SelectItem>
                    <SelectItem value="90">90 jours</SelectItem>
                    <SelectItem value="180">180 jours</SelectItem>
                    <SelectItem value="365">365 jours</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1">
                <MonteCarloCard monteCarlo={monteCarlo} />
              </div>
            </div>
          )}
          {stressTest && stressTest.scenarios.length > 0 && (
            <StressTestCard
              scenarios={stressTest.scenarios}
              totalValue={stressTest.total_value}
              currency={stressTest.currency}
              maxDrawdown={stressTest.max_drawdown}
            />
          )}
        </div>
      )}

      {/* Beta + recommandations de diversification */}
      {((betaData && betaData.assets.length > 0) || (diversification && diversification.recommendations.length > 0)) && (
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          {betaData && betaData.assets.length > 0 && (
            <BetaCard betaData={betaData} betaDays={betaDays} periodDays={periodDays} />
          )}
          {diversification && (
            <DiversificationRecommendations diversification={diversification} />
          )}
        </div>
      )}

      <PerformanceCharts analytics={analytics} />

      {/* Matrice de corrélation */}
      {correlation && correlation.symbols.length > 1 && (
        <CorrelationMatrix correlation={correlation} days={periodDays || undefined} />
      )}

      {/* Performance par période */}
      {performance && <TopWorstPerformers performance={performance} />}

      {/* Pied : horodatage du diagnostic santé */}
      {health && (
        <p className="text-xs text-muted-foreground text-center">
          Analyse de santé générée le {new Date(health.generated_at).toLocaleString('fr-FR')}
        </p>
      )}
    </div>
  )
}
