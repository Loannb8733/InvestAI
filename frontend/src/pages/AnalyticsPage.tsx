import { useState } from 'react'
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
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Shield,
  Target,
  Activity,
  Loader2,
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
import PortfolioEvolutionChart from '@/components/analytics/PortfolioEvolutionChart'
import MonteCarloCard from '@/components/analytics/MonteCarloCard'
import StressTestCard from '@/components/analytics/StressTestCard'
import CorrelationMatrix from '@/components/analytics/CorrelationMatrix'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

const chartTooltipStyle: React.CSSProperties = {
  backgroundColor: 'hsl(var(--popover))',
  borderColor: 'hsl(var(--border))',
  color: 'hsl(var(--popover-foreground))',
  borderRadius: '0.5rem',
  fontSize: 12,
}

const axisTick = { fill: 'hsl(var(--muted-foreground))', fontSize: 12 }
const axisTickSm = { fill: 'hsl(var(--muted-foreground))', fontSize: 11 }

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

interface Portfolio {
  id: string
  name: string
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
    queryFn: analyticsApi.getXirr,
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

  if (loadingAnalytics || loadingDiversification) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (errorAnalytics) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Analyses</h1>
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <Activity className="h-16 w-16 mx-auto text-red-500" />
              <h2 className="text-xl font-semibold">Erreur de chargement</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Impossible de charger les analyses. Veuillez réessayer.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!analytics || analytics.asset_count === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Analyses</h1>
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <BarChart3 className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold">Aucune donnée à analyser</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Ajoutez des actifs à vos portefeuilles pour voir les analyses détaillées.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Safe number formatting with fallback for null/undefined values
  const safeFixed = (v: number | null | undefined, d: number): string =>
    v == null || isNaN(v) ? '—' : v.toFixed(d)

  // Prepare chart data
  const allocationByTypeData = Object.entries(analytics.allocation_by_type || {}).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: Math.round(value * 10) / 10,
  }))

  const allocationByAssetData = Object.entries(analytics.allocation_by_asset || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, value]) => ({
      name,
      value: Math.round(value * 10) / 10,
    }))

  const performanceData = analytics.assets
    .sort((a, b) => b.gain_loss_percent - a.gain_loss_percent)
    .slice(0, 10)
    .map((asset) => ({
      name: asset.symbol,
      performance: Math.round(asset.gain_loss_percent * 10) / 10,
      fill: asset.gain_loss_percent >= 0 ? '#10b981' : '#ef4444',
    }))

  // Radar: each metric normalized to 0-100 where higher = better
  const riskScoreData = [
    {
      metric: 'Rendement',
      value: Math.min(100, Math.max(0, analytics.total_gain_loss_percent * 0.5 + 50)),
      fullMark: 100,
    },
    {
      metric: 'Sharpe',
      value: Math.min(100, Math.max(0, analytics.sharpe_ratio * 25 + 50)),
      fullMark: 100,
    },
    {
      metric: 'Diversification',
      value: diversification?.score || 0,
      fullMark: 100,
    },
    {
      metric: 'Stabilité',
      value: Math.min(100, Math.max(0, 100 - Math.abs(analytics.max_drawdown) * 1.25)),
      fullMark: 100,
    },
    {
      metric: 'Sortino',
      value: Math.min(100, Math.max(0, analytics.sortino_ratio * 25 + 50)),
      fullMark: 100,
    },
  ]

  const chartHistoricalData = historicalData?.map((point) => ({
    date: point.date,
    fullDate: point.full_date || point.date,
    value: point.value,
    invested: point.invested || 0,
    gain: (point.value || 0) - (point.invested || 0),
  })) || []

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'text-red-500'
      case 'medium': return 'text-yellow-500'
      default: return 'text-blue-500'
    }
  }

  const getSeverityBg = (severity: string) => {
    switch (severity) {
      case 'high': return 'bg-red-500/10 border-red-500/20'
      case 'medium': return 'bg-yellow-500/10 border-yellow-500/20'
      default: return 'bg-blue-500/10 border-blue-500/20'
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
          <h1 className="text-3xl font-bold">Analyses</h1>
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
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/20 p-3">
          <Info className="h-4 w-4 text-amber-500 flex-shrink-0" />
          <p className="text-sm text-amber-700 dark:text-amber-400">{analytics.interpretations.global}</p>
        </div>
      )}

      {/* Key Metrics — Row 1: Core risk */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="volatility">
              <CardTitle className="text-sm font-medium">Volatilité</CardTitle>
            </MetricWithTooltip>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{safeFixed(analytics.portfolio_volatility, 1)}%</div>
            <p className="text-xs text-muted-foreground">
              {analytics.portfolio_volatility < 30 ? 'Faible' : analytics.portfolio_volatility < 60 ? 'Modérée' : 'Élevée'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="sharpe">
              <CardTitle className="text-sm font-medium">Sharpe</CardTitle>
            </MetricWithTooltip>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(analytics.sharpe_ratio ?? 0) >= 1 ? 'text-green-500' : (analytics.sharpe_ratio ?? 0) >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>
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

        <Card className="relative ring-1 ring-blue-500/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <MetricWithTooltip metricKey="sortino">
                <CardTitle className="text-sm font-medium">Sortino</CardTitle>
              </MetricWithTooltip>
              <span className="inline-flex items-center gap-0.5 rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
                <Zap className="h-2.5 w-2.5" /> Crypto
              </span>
            </div>
            <Shield className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(analytics.sortino_ratio ?? 0) >= 1 ? 'text-green-500' : (analytics.sortino_ratio ?? 0) >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>
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

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="diversification">
              <CardTitle className="text-sm font-medium">Diversification</CardTitle>
            </MetricWithTooltip>
            <PieChartIcon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(diversification?.score || 0) >= 60 ? 'text-green-500' : (diversification?.score || 0) >= 40 ? 'text-yellow-500' : 'text-red-500'}`}>
              {safeFixed(diversification?.score, 0)}/100
            </div>
            <p className="text-xs text-muted-foreground">{diversification?.rating}</p>
          </CardContent>
        </Card>
      </div>

      {/* Key Metrics — Row 2: More risk + XIRR */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="var">
              <CardTitle className="text-sm font-medium">VaR 95%</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
              {analytics.var_95 != null ? formatCurrency(Math.abs(analytics.var_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.var_95_description || 'Perte max/jour (95%)'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="cvar">
              <CardTitle className="text-sm font-medium">CVaR (ES)</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
              {analytics.cvar_95 != null ? formatCurrency(Math.abs(analytics.cvar_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">Expected Shortfall</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="maxdd">
              <CardTitle className="text-sm font-medium">Max Drawdown</CardTitle>
            </MetricWithTooltip>
            <TrendingDown className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">
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

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="xirr">
              <CardTitle className="text-sm font-medium">XIRR</CardTitle>
            </MetricWithTooltip>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {xirrData?.xirr != null ? (
              <>
                <div className={`text-2xl font-bold ${xirrData.xirr >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {xirrData.xirr > 0 ? '+' : ''}{xirrData.xirr.toFixed(2)}%
                </div>
                <p className="text-xs text-muted-foreground">Rendement annualisé réel</p>
              </>
            ) : (
              <>
                <div className="text-2xl font-bold text-muted-foreground">—</div>
                <p className="text-xs text-muted-foreground">Pas assez de données</p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Allocation by Type */}
        <Card>
          <CardHeader>
            <CardTitle>Répartition par classe d'actifs</CardTitle>
          </CardHeader>
          <CardContent>
            {allocationByTypeData.length <= 1 ? (
              <div className="h-64 flex flex-col items-center justify-center text-center">
                <div className="h-24 w-24 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: `${COLORS[0]}20` }}>
                  <span className="text-2xl font-bold" style={{ color: COLORS[0] }}>100%</span>
                </div>
                <p className="text-sm font-medium">{allocationByTypeData[0]?.name || 'N/A'}</p>
                <p className="text-xs text-muted-foreground mt-1">Classe unique — diversifiez pour voir la répartition</p>
              </div>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={allocationByTypeData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={2}
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}%`}
                    >
                      {allocationByTypeData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip contentStyle={chartTooltipStyle} formatter={(value: number) => `${value}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Risk Radar */}
        <Card>
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
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={riskScoreData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: 'currentColor', fontSize: 11 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: 'currentColor', fontSize: 10 }} />
                  <Radar name="Score" dataKey="value" stroke="hsl(var(--chart-1))" fill="hsl(var(--chart-1))" fillOpacity={0.5} />
                  <RechartsTooltip contentStyle={chartTooltipStyle} formatter={(value: number) => `${value.toFixed(0)}/100`} />
                </RadarChart>
              </ResponsiveContainer>
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
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shuffle className="h-5 w-5 text-blue-500" />
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
                        <div className="flex items-start gap-2 p-3 rounded-md bg-yellow-500/10 border border-yellow-500/30 text-sm">
                          <Info className="h-4 w-4 text-yellow-500 mt-0.5 shrink-0" />
                          <p className="text-yellow-600 dark:text-yellow-400">
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
                                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${weight}%` }} />
                              </div>
                              <span className="text-xs font-mono w-12 text-right">{weight.toFixed(1)}%</span>
                              <span className={`text-xs font-mono w-16 text-right ${diff > 0 ? 'text-green-500' : diff < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
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
                    <div className="text-lg font-bold text-green-500">{optimization.expected_return > 0 ? '+' : ''}{optimization.expected_return.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Rendement espéré</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold">{optimization.expected_volatility.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Volatilité</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-blue-500">{optimization.sharpe_ratio.toFixed(2)}</div>
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
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-blue-500" />
                Beta vs Benchmark
              </CardTitle>
              <CardDescription>
                Sensibilité de vos actifs par rapport au marché
                {periodDays > 0 && periodDays < 30 && (
                  <span className="block text-xs text-yellow-500 mt-1">
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
                      <div className={`text-lg font-bold ${betaData.portfolio_beta_crypto > 1 ? 'text-red-500' : betaData.portfolio_beta_crypto > 0.5 ? 'text-yellow-500' : 'text-green-500'}`}>
                        {betaData.portfolio_beta_crypto.toFixed(2)}
                      </div>
                      <div className="text-xs text-muted-foreground">Beta vs BTC</div>
                    </div>
                  )}
                  {betaData.portfolio_beta_stock != null && (
                    <div className="text-center">
                      <div className={`text-lg font-bold ${betaData.portfolio_beta_stock > 1 ? 'text-red-500' : betaData.portfolio_beta_stock > 0.5 ? 'text-yellow-500' : 'text-green-500'}`}>
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
                              className={`h-full rounded-full absolute ${asset.beta > 1 ? 'bg-red-500' : asset.beta > 0.5 ? 'bg-yellow-500' : 'bg-green-500'}`}
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
      <Card>
        <CardHeader>
          <CardTitle>Performance par actif</CardTitle>
          <CardDescription>Gains/pertes en pourcentage (top 10)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={performanceData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={axisTick} />
                <YAxis type="category" dataKey="name" width={60} tick={axisTick} />
                <RechartsTooltip contentStyle={chartTooltipStyle} formatter={(value: number) => `${value}%`} />
                <Bar dataKey="performance" radius={4}>
                  {performanceData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Allocation by Asset */}
      <Card>
        <CardHeader>
          <CardTitle>Top 10 positions</CardTitle>
          <CardDescription>Répartition par actif</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={allocationByAssetData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="name" tick={axisTickSm} />
                <YAxis tickFormatter={(v) => `${v}%`} tick={axisTickSm} />
                <RechartsTooltip contentStyle={chartTooltipStyle} formatter={(value: number) => `${value}%`} />
                <Bar dataKey="value" fill="hsl(var(--chart-1))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Correlation Matrix */}
      {correlation && correlation.symbols.length > 1 && (
        <CorrelationMatrix correlation={correlation} days={periodDays || undefined} />
      )}

      {/* Recommendations */}
      {diversification && diversification.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-yellow-500" />
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
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-green-500">
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
                      <span className="text-green-500 font-medium">+{item.gain_loss_percent.toFixed(2)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">Aucun gain sur cette période</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-red-500">
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
                      <span className="text-red-500 font-medium">{item.gain_loss_percent.toFixed(2)}%</span>
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
