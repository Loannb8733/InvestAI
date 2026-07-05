import { useMemo, useState } from 'react'
import type { PortfolioSummary as Portfolio } from '@/types'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { analyticsApi, dashboardApi, portfoliosApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { ResponsivePie } from '@nivo/pie'
import { ResponsiveBar } from '@nivo/bar'
import { ResponsiveRadar } from '@nivo/radar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import {
  TrendingUp,
  TrendingDown,
  Shield,
  Target,
  Activity,
  PieChart as PieChartIcon,
  BarChart3,
  Info,
  HelpCircle,
  FileSpreadsheet,
  Zap,
  Percent,
  ArrowDownRight,
  Shuffle,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import SpotlightGroup from '@/components/ui/spotlight-group'
import EmptyState from '@/components/ui/empty-state'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import PortfolioEvolutionChart from '@/components/analytics/PortfolioEvolutionChart'
import MonteCarloCard from '@/components/analytics/MonteCarloCard'
import StressTestCard from '@/components/analytics/StressTestCard'
import CorrelationMatrix from '@/components/analytics/CorrelationMatrix'

const COLORS = ['oklch(var(--chart-5))', 'oklch(var(--chart-3))', 'oklch(var(--chart-1))', 'oklch(var(--chart-4))', 'oklch(var(--chart-2))', 'oklch(var(--chart-2))', 'oklch(var(--chart-5))', 'oklch(var(--chart-3))']

// Token order matching COLORS, for resolving Nivo-compatible rgb() colors
const COLOR_TOKENS = ['--chart-5', '--chart-3', '--chart-1', '--chart-4', '--chart-2', '--chart-2', '--chart-5', '--chart-3']

interface Analytics {
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

interface Diversification {
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

interface Correlation {
  symbols: string[]
  matrix: number[][]
  strongly_correlated: [string, string, number][]
  negatively_correlated: [string, string, number][]
}

interface PerformanceItem {
  symbol: string
  name: string
  asset_type: string
  gain_loss_percent: number
}

interface PerformanceSummary {
  top_gainers: PerformanceItem[]
  top_losers: PerformanceItem[]
}

interface HistoricalDataPoint {
  date: string
  full_date?: string
  value: number
  invested?: number
  gain_loss?: number
}

interface MonteCarloData {
  percentiles: Record<string, number>
  expected_return: number
  prob_positive: number
  prob_loss_10: number
  prob_ruin: number
  simulations: number
  horizon_days: number
}

interface StressScenario {
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

interface StressTestData {
  total_value: number
  currency: string
  scenarios: StressScenario[]
  max_drawdown: {
    value: number
    scenario: string
    estimated_recovery_months: number
  } | null
}

interface BetaAsset {
  symbol: string
  asset_type: string
  beta: number | null
  benchmark: string
  interpretation: string
  value: number
}

interface BetaData {
  assets: BetaAsset[]
  portfolio_beta_crypto: number | null
  portfolio_beta_stock: number | null
  benchmarks: Record<string, string>
}

interface OptimizeData {
  weights: Record<string, number>
  expected_return: number
  expected_volatility: number
  sharpe_ratio: number
}

// Metric explanation tooltips
const metricExplanations: Record<string, { title: string; description: string }> = {
  volatility: {
    title: 'Volatilité',
    description: 'Variation annualisée des prix (σ√252). Crypto: 50-100% normal. Actions: 15-25% typique.',
  },
  sharpe: {
    title: 'Ratio de Sharpe',
    description: 'Rendement excédentaire / volatilité. > 1 = bon, > 2 = excellent, < 0 = rendement sous le taux sans risque.',
  },
  sortino: {
    title: 'Ratio de Sortino',
    description: 'Comme le Sharpe, mais ne pénalise que la volatilité baissière. Plus pertinent car la hausse n\'est pas un risque.',
  },
  calmar: {
    title: 'Ratio de Calmar',
    description: 'Rendement annualisé / max drawdown. Mesure la capacité à se remettre des pertes. > 1 = bon.',
  },
  var: {
    title: 'VaR 95%',
    description: 'Perte max journalière avec 95% de confiance. Basé sur l\'historique réel des rendements.',
  },
  cvar: {
    title: 'CVaR / Expected Shortfall',
    description: 'Perte moyenne quand on dépasse le VaR. Plus conservateur — mesure le risque extrême.',
  },
  diversification: {
    title: 'Score de Diversification',
    description: 'Composite: nb actifs + nb classes + concentration (HHI). 0-40: Faible, 40-60: Moyen, 60-80: Bon, 80+: Excellent.',
  },
  maxdd: {
    title: 'Max Drawdown',
    description: 'Plus grande perte depuis un sommet historique. Mesure le pire scénario vécu.',
  },
  xirr: {
    title: 'XIRR',
    description: 'Taux de rendement interne annualisé. Tient compte du timing de chaque investissement (DCA vs lump sum).',
  },
}

const MetricWithTooltip = ({ metricKey, children }: { metricKey: string; children: React.ReactNode }) => {
  const explanation = metricExplanations[metricKey]
  if (!explanation) return <>{children}</>
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1 cursor-help" aria-label={`Aide sur ${explanation.title}`}>
            {children}
            <HelpCircle className="h-3 w-3 text-muted-foreground" />
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="font-medium">{explanation.title}</p>
          <p className="text-xs text-muted-foreground mt-1">{explanation.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export default function AnalyticsPage() {
  const [period, setPeriod] = useState('30d')
  const [selectedPortfolio, setSelectedPortfolio] = useState<string>('all')
  const { theme, color } = useNivoTheme()

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: queryKeys.portfolios.list(),
    queryFn: portfoliosApi.list,
    staleTime: 60_000,
  })

  const analyticsQueryOpts = { retry: 1, staleTime: 5 * 60 * 1000, refetchOnWindowFocus: false } as const

  // Map period label to days for all analytics queries
  const periodDays = period === '1d' ? 1 : period === '7d' ? 7 : period === '30d' ? 30 : period === '90d' ? 90 : period === '1y' ? 365 : period === 'all' ? 0 : 365
  const portfolioParam = selectedPortfolio === 'all' ? undefined : selectedPortfolio

  const { data: analytics, isLoading: loadingAnalytics, isError: errorAnalytics } = useQuery<Analytics>({
    queryKey: queryKeys.analytics.global(portfolioParam, periodDays),
    queryFn: () => selectedPortfolio === 'all'
      ? analyticsApi.getGlobal(periodDays)
      : analyticsApi.getPortfolio(selectedPortfolio, periodDays),
    ...analyticsQueryOpts,
    // Page shows its own isError card → opt out of the global error toast (no double-report).
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

  const monteCarloHorizon = Math.max(7, periodDays || 90)
  const { data: monteCarlo } = useQuery<MonteCarloData>({
    queryKey: queryKeys.analytics.monteCarlo(portfolioParam, monteCarloHorizon),
    queryFn: () => analyticsApi.getMonteCarlo(monteCarloHorizon, portfolioParam),
    enabled: !!analytics && analytics.asset_count > 0 && periodDays !== 1,
    ...analyticsQueryOpts,
  })

  const { data: xirrData } = useQuery<{ xirr: number | null }>({
    queryKey: queryKeys.analytics.xirr(portfolioParam),
    queryFn: () => analyticsApi.getXirr(portfolioParam ?? undefined),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const optimizeDays = Math.max(30, periodDays || 90)
  const { data: optimization } = useQuery<OptimizeData>({
    queryKey: queryKeys.analytics.optimize(portfolioParam, optimizeDays),
    queryFn: () => analyticsApi.getOptimize('max_sharpe', optimizeDays),
    enabled: !!analytics && analytics.asset_count >= 2,
    ...analyticsQueryOpts,
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

  // ── Memoize chart datasets (hook order must be stable, so this runs BEFORE
  //    the early returns below; the resulting arrays are unused when analytics
  //    is undefined / empty because those branches return before any chart is
  //    rendered).
  const allocationByTypeData = useMemo(
    () =>
      Object.entries(analytics?.allocation_by_type || {}).map(([name, value], index) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: Math.round(value * 10) / 10,
        color: color(COLOR_TOKENS[index % COLOR_TOKENS.length]),
      })),
    [analytics?.allocation_by_type, color]
  )

  const allocationByAssetData = useMemo(
    () =>
      Object.entries(analytics?.allocation_by_asset || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([name, value]) => ({
          name,
          value: Math.round(value * 10) / 10,
        })),
    [analytics?.allocation_by_asset]
  )

  const performanceData = useMemo(
    () =>
      [...(analytics?.assets || [])]
        .sort((a, b) => b.gain_loss_percent - a.gain_loss_percent)
        .slice(0, 10)
        .map((asset) => ({
          name: asset.symbol,
          performance: Math.round(asset.gain_loss_percent * 10) / 10,
          fill: asset.gain_loss_percent >= 0 ? color('--chart-3') : color('--chart-4'),
        })),
    [analytics?.assets, color]
  )

  const riskScoreData = useMemo(
    () => [
      {
        metric: 'Rendement',
        value: Math.min(100, Math.max(0, (analytics?.total_gain_loss_percent ?? 0) * 0.5 + 50)),
        fullMark: 100,
      },
      {
        metric: 'Sharpe',
        value: Math.min(100, Math.max(0, (analytics?.sharpe_ratio ?? 0) * 25 + 50)),
        fullMark: 100,
      },
      {
        metric: 'Diversification',
        value: diversification?.score || 0,
        fullMark: 100,
      },
      {
        metric: 'Stabilité',
        value: Math.min(100, Math.max(0, 100 - Math.abs(analytics?.max_drawdown ?? 0) * 1.25)),
        fullMark: 100,
      },
      {
        metric: 'Sortino',
        value: Math.min(100, Math.max(0, (analytics?.sortino_ratio ?? 0) * 25 + 50)),
        fullMark: 100,
      },
    ],
    [
      analytics?.total_gain_loss_percent,
      analytics?.sharpe_ratio,
      analytics?.max_drawdown,
      analytics?.sortino_ratio,
      diversification?.score,
    ]
  )

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
        <h1 className="text-3xl font-serif font-medium">Analyses</h1>
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
      <div className="space-y-6">
        <h1 className="text-3xl font-serif font-medium">Analyses</h1>
        <EmptyState
          variant="error"
          icon={Activity}
          title="Erreur de chargement"
          description="Impossible de charger les analyses. Veuillez réessayer."
        />
      </div>
    )
  }

  if (!analytics || analytics.asset_count === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-serif font-medium">Analyses</h1>
        <EmptyState
          icon={BarChart3}
          title="Aucune donnée à analyser"
          description="Ajoutez des actifs à vos portefeuilles pour voir les analyses détaillées."
        />
      </div>
    )
  }

  // Safe number formatting with fallback for null/undefined values
  const safeFixed = (v: number | null | undefined, d: number): string =>
    v == null || isNaN(v) ? '—' : v.toFixed(d)

  // (chart datasets are memoized above — kept before the early returns to
  // satisfy the rules of hooks).

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'text-loss'
      case 'medium': return 'text-warning'
      default: return 'text-accent'
    }
  }

  const getSeverityBg = (severity: string) => {
    switch (severity) {
      case 'high': return 'bg-loss/10 border-loss/20'
      case 'medium': return 'bg-warning/10 border-warning/20'
      default: return 'bg-accent/10 border-accent/20'
    }
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
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-serif font-medium">Analyses</h1>
          <p className="text-muted-foreground">
            Métriques avancées et analyse de votre portefeuille
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={selectedPortfolio} onValueChange={setSelectedPortfolio}>
            <SelectTrigger className="w-40">
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
            <SelectTrigger className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1d">24h</SelectItem>
              <SelectItem value="7d">7 jours</SelectItem>
              <SelectItem value="30d">30 jours</SelectItem>
              <SelectItem value="90d">90 jours</SelectItem>
              <SelectItem value="1y">1 an</SelectItem>
              <SelectItem value="all">Tout</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={exportToCSV}>
            <FileSpreadsheet className="h-4 w-4 mr-1" />
            CSV
          </Button>
        </div>
      </div>

      {/* Portfolio Evolution Chart */}
      <PortfolioEvolutionChart chartHistoricalData={chartHistoricalData} />

      {/* Short history warning */}
      {analytics.interpretations?.global && (
        <div className="flex items-center gap-2 rounded-lg border border-warning dark:border-warning bg-warning dark:bg-warning/20 p-3">
          <Info className="h-4 w-4 text-warning flex-shrink-0" />
          <p className="text-sm text-warning dark:text-warning">{analytics.interpretations.global}</p>
        </div>
      )}

      {/* Key Metrics — Row 1: Core risk */}
      <SpotlightGroup className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="volatility">
              <CardTitle className="text-sm font-medium">Volatilité</CardTitle>
            </MetricWithTooltip>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium">{safeFixed(analytics.portfolio_volatility, 1)}%</div>
            <p className="text-xs text-muted-foreground">
              {analytics.portfolio_volatility < 30 ? 'Faible' : analytics.portfolio_volatility < 60 ? 'Modérée' : 'Élevée'}
            </p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="sharpe">
              <CardTitle className="text-sm font-medium">Sharpe</CardTitle>
            </MetricWithTooltip>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(analytics.sharpe_ratio ?? 0) >= 1 ? 'text-gain' : (analytics.sharpe_ratio ?? 0) >= 0 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(analytics.sharpe_ratio, 2)}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.sharpe_ratio >= 2 ? 'Excellent' : analytics.sharpe_ratio >= 1 ? 'Bon' : analytics.sharpe_ratio >= 0 ? 'Moyen' : 'Faible'}
            </p>
            {analytics.interpretations?.sharpe && (
              <p className="text-xs text-muted-foreground/80 mt-1.5 italic leading-snug">
                {analytics.interpretations.sharpe}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card relative ring-1 ring-accent/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <MetricWithTooltip metricKey="sortino">
                <CardTitle className="text-sm font-medium">Sortino</CardTitle>
              </MetricWithTooltip>
              <span className="inline-flex items-center gap-0.5 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent dark:text-accent">
                <Zap className="h-2.5 w-2.5" /> Crypto
              </span>
            </div>
            <Shield className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(analytics.sortino_ratio ?? 0) >= 1 ? 'text-gain' : (analytics.sortino_ratio ?? 0) >= 0 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(analytics.sortino_ratio, 2)}
            </div>
            <p className="text-xs text-muted-foreground">
              Ne punit pas les hausses explosives
            </p>
            {analytics.interpretations?.sortino && (
              <p className="text-xs text-muted-foreground/80 mt-1.5 italic leading-snug">
                {analytics.interpretations.sortino}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="diversification">
              <CardTitle className="text-sm font-medium">Diversification</CardTitle>
            </MetricWithTooltip>
            <PieChartIcon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(diversification?.score || 0) >= 60 ? 'text-gain' : (diversification?.score || 0) >= 40 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(diversification?.score, 0)}/100
            </div>
            <p className="text-xs text-muted-foreground">{diversification?.rating}</p>
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Key Metrics — Row 2: More risk + XIRR */}
      <SpotlightGroup className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="var">
              <CardTitle className="text-sm font-medium">VaR 95%</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {analytics.var_95 != null ? formatCurrency(Math.abs(analytics.var_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.var_95_description || 'Perte max/jour (95%)'}
            </p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="cvar">
              <CardTitle className="text-sm font-medium">CVaR (ES)</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {analytics.cvar_95 != null ? formatCurrency(Math.abs(analytics.cvar_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">Expected Shortfall</p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="maxdd">
              <CardTitle className="text-sm font-medium">Max Drawdown</CardTitle>
            </MetricWithTooltip>
            <TrendingDown className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {safeFixed(analytics.max_drawdown, 1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              Calmar: {safeFixed(analytics.calmar_ratio, 2)}
            </p>
            {analytics.interpretations?.calmar && (
              <p className="text-xs text-muted-foreground/80 mt-1 italic leading-snug">
                {analytics.interpretations.calmar}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="xirr">
              <CardTitle className="text-sm font-medium">XIRR</CardTitle>
            </MetricWithTooltip>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {xirrData?.xirr != null ? (
              <>
                <div className={`text-2xl font-serif font-medium ${xirrData.xirr >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {xirrData.xirr > 0 ? '+' : ''}{xirrData.xirr.toFixed(2)}%
                </div>
                <p className="text-xs text-muted-foreground">Rendement annualisé réel</p>
              </>
            ) : (
              <>
                <div className="text-2xl font-serif font-medium text-muted-foreground">—</div>
                <p className="text-xs text-muted-foreground">Pas assez de données</p>
              </>
            )}
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Charts Row */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Allocation by Type */}
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Répartition par classe d'actifs</CardTitle>
          </CardHeader>
          <CardContent>
            {allocationByTypeData.length <= 1 ? (
              <div className="h-64 flex flex-col items-center justify-center text-center">
                <div className="h-24 w-24 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: `${COLORS[0]}20` }}>
                  <span className="text-2xl font-serif font-medium" style={{ color: COLORS[0] }}>100%</span>
                </div>
                <p className="text-sm font-medium">{allocationByTypeData[0]?.name || 'N/A'}</p>
                <p className="text-xs text-muted-foreground mt-1">Classe unique — diversifiez pour voir la répartition</p>
              </div>
            ) : (
              <div className="h-64">
                <ResponsivePie
                  data={allocationByTypeData.map((d) => ({
                    id: d.name,
                    label: d.name,
                    value: d.value,
                    color: d.color,
                  }))}
                  theme={theme}
                  margin={{ top: 12, right: 12, bottom: 12, left: 12 }}
                  innerRadius={0.62}
                  padAngle={2}
                  cornerRadius={3}
                  colors={{ datum: 'data.color' }}
                  borderWidth={2}
                  borderColor={color('--background')}
                  arcLabelsSkipAngle={12}
                  arcLabel={(d) => `${d.value}%`}
                  arcLabelsTextColor={color('--background')}
                  enableArcLinkLabels={false}
                  isInteractive
                  tooltip={({ datum }) => (
                    <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                      <p className="text-sm font-medium">{datum.label}</p>
                      <p className="mt-0.5 font-mono text-sm tabular-nums">{datum.value}%</p>
                    </div>
                  )}
                />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Risk Radar */}
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Profil de risque
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger aria-label="Aide sur le profil de risque">
                    <HelpCircle className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p className="text-xs">Plus la surface est grande, meilleur est le profil. Rendement, Sharpe et Sortino centrés à 50 (neutre). Stabilité = 100 - |drawdown|.</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveRadar
                data={riskScoreData}
                keys={['value']}
                indexBy="metric"
                theme={theme}
                maxValue={100}
                margin={{ top: 28, right: 48, bottom: 28, left: 48 }}
                gridLevels={5}
                gridShape="circular"
                gridLabelOffset={12}
                colors={[color('--chart-4')]}
                fillOpacity={0.2}
                borderWidth={2}
                borderColor={{ from: 'color' }}
                dotSize={6}
                dotColor={color('--chart-4')}
                dotBorderWidth={2}
                dotBorderColor={color('--background')}
                enableDotLabel={false}
                isInteractive
                motionConfig="gentle"
                sliceTooltip={({ index, data }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="text-sm font-medium">{index}</p>
                    <p className="mt-0.5 font-mono text-sm tabular-nums text-muted-foreground">
                      {(data[0]?.value as number).toFixed(0)}/100
                    </p>
                  </div>
                )}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Monte Carlo + Optimization */}
      {(monteCarlo?.simulations || optimization) && (
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Monte Carlo */}
        {monteCarlo && monteCarlo.simulations > 0 && (
          <MonteCarloCard monteCarlo={monteCarlo} />
        )}

        {/* MPT Optimization */}
        {optimization && (
          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shuffle className="h-5 w-5 text-accent" />
                Allocation optimale (Markowitz)
              </CardTitle>
              <CardDescription>
                Portefeuille maximisant le Sharpe ratio
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Optimal weights */}
                {(() => {
                  const significantWeights = Object.entries(optimization.weights)
                    .sort((a, b) => b[1] - a[1])
                    .filter(([_, w]) => w >= 0.5)
                  const isSingleAsset = significantWeights.length === 1 && significantWeights[0][1] >= 99
                  return (
                    <>
                      {isSingleAsset && (
                        <div className="flex items-start gap-2 p-3 rounded-md bg-warning/10 border border-warning/30 text-sm">
                          <Info className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                          <p className="text-warning dark:text-warning">
                            Avec seulement {Object.keys(optimization.weights).length} actif{Object.keys(optimization.weights).length > 1 ? 's' : ''}, l'optimisation concentre tout sur un seul. Ajoutez des actifs diversifiés pour une allocation plus pertinente.
                          </p>
                        </div>
                      )}
                      <div className="space-y-2">
                        {significantWeights.map(([symbol, weight]) => {
                          const current = analytics.allocation_by_asset[symbol] || 0
                          const diff = weight - current
                          return (
                            <div key={symbol} className="flex items-center gap-2">
                              <span className="text-sm font-medium w-16">{symbol}</span>
                              <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                                <div className="h-full bg-accent rounded-full" style={{ width: `${weight}%` }} />
                              </div>
                              <span className="text-xs font-mono w-12 text-right">{weight.toFixed(1)}%</span>
                              <span className={`text-xs font-mono w-16 text-right ${diff > 0 ? 'text-gain' : diff < 0 ? 'text-loss' : 'text-muted-foreground'}`}>
                                {diff > 0 ? '+' : ''}{diff.toFixed(1)}%
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    </>
                  )
                })()}
                {/* Expected metrics */}
                <div className="grid grid-cols-3 gap-3 pt-2 border-t">
                  <div className="text-center">
                    <div className="text-lg font-bold text-gain">{optimization.expected_return > 0 ? '+' : ''}{optimization.expected_return.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Rendement espéré</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold">{optimization.expected_volatility.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Volatilité</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-accent">{optimization.sharpe_ratio.toFixed(2)}</div>
                    <div className="text-xs text-muted-foreground">Sharpe optimal</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
      )}

      {/* Stress Test + Beta */}
      {(stressTest?.scenarios?.length || betaData?.assets?.length) && (
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Stress Test */}
        {stressTest && stressTest.scenarios.length > 0 && (
          <StressTestCard
            scenarios={stressTest.scenarios}
            totalValue={stressTest.total_value}
            currency={stressTest.currency}
            maxDrawdown={stressTest.max_drawdown}
          />
        )}

        {/* Beta vs Benchmark */}
        {betaData && betaData.assets.length > 0 && (
          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-accent" />
                Beta vs Benchmark
              </CardTitle>
              <CardDescription>
                Sensibilité de vos actifs par rapport au marché
                {periodDays > 0 && periodDays < 30 && (
                  <span className="block text-xs text-warning mt-1">
                    Min. 30 jours requis pour le beta (calculé sur {betaDays}j)
                  </span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {/* Portfolio betas */}
                <div className="grid grid-cols-2 gap-3 pb-3 border-b">
                  {betaData.portfolio_beta_crypto != null && (
                    <div className="text-center">
                      <div className={`text-lg font-bold ${betaData.portfolio_beta_crypto > 1 ? 'text-loss' : betaData.portfolio_beta_crypto > 0.5 ? 'text-warning' : 'text-gain'}`}>
                        {betaData.portfolio_beta_crypto.toFixed(2)}
                      </div>
                      <div className="text-xs text-muted-foreground">Beta vs BTC</div>
                    </div>
                  )}
                  {betaData.portfolio_beta_stock != null && (
                    <div className="text-center">
                      <div className={`text-lg font-bold ${betaData.portfolio_beta_stock > 1 ? 'text-loss' : betaData.portfolio_beta_stock > 0.5 ? 'text-warning' : 'text-gain'}`}>
                        {betaData.portfolio_beta_stock.toFixed(2)}
                      </div>
                      <div className="text-xs text-muted-foreground">Beta vs SPY</div>
                    </div>
                  )}
                </div>

                {/* Per-asset betas */}
                <div className="space-y-2">
                  {betaData.assets.slice(0, 8).map((asset) => (
                    <div key={asset.symbol} className="flex items-center gap-2">
                      <span className="text-sm font-medium w-14">{asset.symbol}</span>
                      <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden relative">
                        {asset.beta != null && (
                          <>
                            {/* Reference line at beta=1 */}
                            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-foreground/20" />
                            <div
                              className={`h-full rounded-full absolute ${asset.beta > 1 ? 'bg-loss' : asset.beta > 0.5 ? 'bg-warning' : 'bg-gain'}`}
                              style={{
                                width: `${Math.min(100, Math.abs(asset.beta) * 50)}%`,
                                left: asset.beta >= 0 ? '0%' : undefined,
                                right: asset.beta < 0 ? '50%' : undefined,
                              }}
                            />
                          </>
                        )}
                      </div>
                      <span className="text-xs font-mono w-10 text-right">
                        {asset.beta != null ? asset.beta.toFixed(2) : '—'}
                      </span>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger aria-label={`Aide sur le beta de ${asset.symbol}`}>
                            <HelpCircle className="h-3 w-3 text-muted-foreground" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            <p className="text-xs">{asset.interpretation}</p>
                            <p className="text-xs text-muted-foreground mt-1">Benchmark: {asset.benchmark}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
      )}

      {/* Performance Chart */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Performance par actif</CardTitle>
          <CardDescription>Gains/pertes en pourcentage (top 10)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveBar
              data={performanceData}
              keys={['performance']}
              indexBy="name"
              layout="horizontal"
              theme={theme}
              margin={{ top: 8, right: 24, bottom: 32, left: 64 }}
              padding={0.3}
              colors={({ data }) => data.fill}
              borderRadius={4}
              enableLabel={false}
              enableGridX
              enableGridY={false}
              axisBottom={{ tickSize: 0, tickPadding: 8, format: (v) => `${v}%` }}
              axisLeft={{ tickSize: 0, tickPadding: 8 }}
              valueScale={{ type: 'linear' }}
              tooltip={({ indexValue, value, color: barColor }) => (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: barColor }} />
                    <span className="text-xs text-muted-foreground">{indexValue}</span>
                  </span>
                  <p className="mt-0.5 font-mono text-sm tabular-nums">{value}%</p>
                </div>
              )}
              animate
              motionConfig="gentle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Allocation by Asset */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Top 10 positions</CardTitle>
          <CardDescription>Répartition par actif</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveBar
              data={allocationByAssetData}
              keys={['value']}
              indexBy="name"
              theme={theme}
              margin={{ top: 8, right: 16, bottom: 40, left: 48 }}
              padding={0.3}
              colors={() => color('--chart-1')}
              borderRadius={4}
              enableLabel={false}
              enableGridY
              enableGridX={false}
              axisBottom={{ tickSize: 0, tickPadding: 8 }}
              axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}%` }}
              valueScale={{ type: 'linear' }}
              tooltip={({ indexValue, value }) => (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                  <p className="text-xs text-muted-foreground">{indexValue}</p>
                  <p className="mt-0.5 font-mono text-sm tabular-nums">{value}%</p>
                </div>
              )}
              animate
              motionConfig="gentle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Correlation Matrix */}
      {correlation && correlation.symbols.length > 1 && (
        <CorrelationMatrix correlation={correlation} days={periodDays || undefined} />
      )}

      {/* Recommendations */}
      {diversification && diversification.recommendations.length > 0 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-warning" />
              Recommandations
            </CardTitle>
            <CardDescription>Actions suggérées pour améliorer votre portefeuille</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              {diversification.recommendations.map((rec, index) => (
                <div key={index} className={`p-4 rounded-lg border ${getSeverityBg(rec.severity)}`}>
                  <div className="flex items-start gap-3">
                    <Info className={`h-5 w-5 mt-0.5 shrink-0 ${getSeverityColor(rec.severity)}`} />
                    <div>
                      <p className="font-medium text-sm">{rec.message}</p>
                      <p className="text-xs text-muted-foreground mt-1">{rec.action}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top / Worst performers */}
      {performance && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-gain">
                <TrendingUp className="h-5 w-5" />
                Meilleurs performers
              </CardTitle>
            </CardHeader>
            <CardContent>
              {performance.top_gainers && performance.top_gainers.length > 0 ? (
                <div className="space-y-3">
                  {performance.top_gainers.map((item: PerformanceItem) => (
                    <div key={item.symbol} className="flex items-center justify-between">
                      <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                      <span className="text-gain font-medium">+{item.gain_loss_percent.toFixed(2)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">Aucun gain sur cette période</p>
              )}
            </CardContent>
          </Card>

          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-loss">
                <TrendingDown className="h-5 w-5" />
                Moins bons performers
              </CardTitle>
            </CardHeader>
            <CardContent>
              {performance.top_losers && performance.top_losers.length > 0 ? (
                <div className="space-y-3">
                  {performance.top_losers.map((item: PerformanceItem) => (
                    <div key={item.symbol} className="flex items-center justify-between">
                      <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                      <span className="text-loss font-medium">{item.gain_loss_percent.toFixed(2)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">Aucune perte sur cette période</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
