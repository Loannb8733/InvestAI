import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
  Legend,
  AreaChart,
  Area,
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Shield,
  AlertTriangle,
  Target,
  Activity,
  Loader2,
  PieChart as PieChartIcon,
  BarChart3,
  Info,
  HelpCircle,
  FileSpreadsheet,
  LineChart as LineChartIcon,
  Zap,
  Percent,
  ArrowDownRight,
  Shuffle,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

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
  simulations: number
  horizon_days: number
}

interface StressScenario {
  name: string
  description: string
  stressed_value: number
  total_loss: number
  total_loss_pct: number
  per_asset: Array<{
    symbol: string
    current_value: number
    stressed_value: number
    loss: number
    shock_pct: number
  }>
}

interface StressTestData {
  total_value: number
  scenarios: StressScenario[]
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
          <div className="flex items-center gap-1 cursor-help">
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
    queryKey: ['portfolios'],
    queryFn: portfoliosApi.list,
  })

  const analyticsQueryOpts = { retry: 1, staleTime: 5 * 60 * 1000, refetchOnWindowFocus: false } as const

  // Map period label to days for all analytics queries
  const periodDays = period === '7d' ? 7 : period === '30d' ? 30 : period === '90d' ? 90 : period === '1y' ? 365 : 365
  const portfolioParam = selectedPortfolio === 'all' ? undefined : selectedPortfolio

  const { data: analytics, isLoading: loadingAnalytics } = useQuery<Analytics>({
    queryKey: ['analytics', selectedPortfolio, periodDays],
    queryFn: () => selectedPortfolio === 'all'
      ? analyticsApi.getGlobal(periodDays)
      : analyticsApi.getPortfolio(selectedPortfolio, periodDays),
    ...analyticsQueryOpts,
  })

  const { data: diversification, isLoading: loadingDiversification } = useQuery<Diversification>({
    queryKey: ['diversification', selectedPortfolio, periodDays],
    queryFn: () => analyticsApi.getDiversification(portfolioParam, periodDays),
    ...analyticsQueryOpts,
  })

  const { data: correlation } = useQuery<Correlation>({
    queryKey: ['correlation', selectedPortfolio, periodDays],
    queryFn: () => analyticsApi.getCorrelation(portfolioParam, periodDays),
    ...analyticsQueryOpts,
  })

  const { data: performance } = useQuery({
    queryKey: ['performance', period],
    queryFn: () => analyticsApi.getPerformance(period),
    ...analyticsQueryOpts,
  })

  const { data: monteCarlo } = useQuery<MonteCarloData>({
    queryKey: ['monteCarlo'],
    queryFn: () => analyticsApi.getMonteCarlo(90),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const { data: xirrData } = useQuery<{ xirr: number | null }>({
    queryKey: ['xirr'],
    queryFn: analyticsApi.getXirr,
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const { data: optimization } = useQuery<OptimizeData>({
    queryKey: ['optimize', periodDays],
    queryFn: () => analyticsApi.getOptimize('max_sharpe'),
    enabled: !!analytics && analytics.asset_count >= 2,
    ...analyticsQueryOpts,
  })

  const { data: stressTest } = useQuery<StressTestData>({
    queryKey: ['stressTest'],
    queryFn: analyticsApi.getStressTest,
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })

  const { data: betaData } = useQuery<BetaData>({
    queryKey: ['beta', periodDays],
    queryFn: () => analyticsApi.getBeta(periodDays),
    enabled: !!analytics && analytics.asset_count > 0,
    ...analyticsQueryOpts,
  })
  const { data: historicalData } = useQuery<HistoricalDataPoint[]>({
    queryKey: ['historicalData', periodDays],
    queryFn: () => dashboardApi.getHistoricalData(periodDays),
  })

  if (loadingAnalytics || loadingDiversification) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
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

  // Prepare chart data
  const allocationByTypeData = Object.entries(analytics.allocation_by_type).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: Math.round(value * 10) / 10,
  }))

  const allocationByAssetData = Object.entries(analytics.allocation_by_asset)
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

  const riskScoreData = [
    { metric: 'Diversification', value: diversification?.score || 0, fullMark: 100 },
    { metric: 'Concentration', value: Math.max(0, 100 - (analytics.concentration_risk * 400)), fullMark: 100 },
    { metric: 'Volatilité', value: Math.max(0, 100 - analytics.portfolio_volatility), fullMark: 100 },
    { metric: 'Sharpe', value: Math.min(100, Math.max(0, analytics.sharpe_ratio * 33 + 50)), fullMark: 100 },
    { metric: 'Nb Actifs', value: Math.min(100, analytics.asset_count * 10), fullMark: 100 },
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
    const headers = ['Actif', 'Type', 'Valeur', 'Performance %', 'Poids %', 'Volatilité', 'Sharpe', 'Sortino', 'Max Drawdown', 'Rendement J']
    const rows = analytics.assets.map(a => [
      a.symbol,
      a.asset_type,
      a.current_value.toFixed(2),
      a.gain_loss_percent.toFixed(2),
      a.weight.toFixed(2),
      a.volatility_30d?.toFixed(2) || 'N/A',
      a.sharpe_ratio?.toFixed(2) || 'N/A',
      a.sortino_ratio?.toFixed(2) || 'N/A',
      a.max_drawdown?.toFixed(2) || 'N/A',
      a.daily_return?.toFixed(2) || 'N/A',
    ])

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `analyse-portefeuille-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
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
              <SelectItem value="all">Tous les portfolios</SelectItem>
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
      {chartHistoricalData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <LineChartIcon className="h-5 w-5" />
              Évolution du portefeuille
            </CardTitle>
            <CardDescription>Valeur totale vs montant investi</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartHistoricalData}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorInvested" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#94a3b8" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} interval="preserveStartEnd" />
                  <YAxis tickFormatter={(v) => formatCurrency(v).replace('€', '')} tick={{ fontSize: 12 }} width={80} />
                  <RechartsTooltip
                    formatter={(value: number, name: string) => [
                      formatCurrency(value),
                      name === 'value' ? 'Valeur' : 'Investi'
                    ]}
                  />
                  <Legend formatter={(value) => value === 'value' ? 'Valeur actuelle' : 'Montant investi'} />
                  <Area type="monotone" dataKey="invested" stroke="#94a3b8" strokeWidth={2} fillOpacity={1} fill="url(#colorInvested)" />
                  <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
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
            <div className="text-2xl font-bold">{analytics.portfolio_volatility.toFixed(1)}%</div>
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
            <div className={`text-2xl font-bold ${analytics.sharpe_ratio >= 1 ? 'text-green-500' : analytics.sharpe_ratio >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>
              {analytics.sharpe_ratio.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.sharpe_ratio >= 2 ? 'Excellent' : analytics.sharpe_ratio >= 1 ? 'Bon' : analytics.sharpe_ratio >= 0 ? 'Moyen' : 'Faible'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="sortino">
              <CardTitle className="text-sm font-medium">Sortino</CardTitle>
            </MetricWithTooltip>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${analytics.sortino_ratio >= 1 ? 'text-green-500' : analytics.sortino_ratio >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>
              {analytics.sortino_ratio.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">
              Risque baissier uniquement
            </p>
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
              {diversification?.score.toFixed(0)}/100
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
              {formatCurrency(Math.abs(analytics.var_95))}
            </div>
            <p className="text-xs text-muted-foreground">Perte max/jour</p>
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
              {formatCurrency(Math.abs(analytics.cvar_95))}
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
              {analytics.max_drawdown.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              Calmar: {analytics.calmar_ratio.toFixed(2)}
            </p>
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
                  {xirrData.xirr > 0 ? '+' : ''}{xirrData.xirr.toFixed(1)}%
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
                  <RechartsTooltip formatter={(value: number) => `${value}%`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Risk Radar */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Profil de risque
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <HelpCircle className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p className="text-xs">Plus la surface est grande, meilleur est le profil. Chaque axe normalisé sur 100.</p>
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
                  <Radar name="Score" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.5} />
                  <RechartsTooltip formatter={(value: number) => `${value.toFixed(0)}/100`} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Monte Carlo + Optimization */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Monte Carlo */}
        {monteCarlo && monteCarlo.simulations > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-purple-500" />
                Simulation Monte Carlo
              </CardTitle>
              <CardDescription>
                {monteCarlo.simulations.toLocaleString()} simulations sur {monteCarlo.horizon_days} jours
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Distribution bars */}
                <div className="space-y-2">
                  {[
                    { label: 'Pessimiste (5%)', value: monteCarlo.percentiles.p5, color: 'bg-red-500' },
                    { label: 'Bas (25%)', value: monteCarlo.percentiles.p25, color: 'bg-orange-500' },
                    { label: 'Médian (50%)', value: monteCarlo.percentiles.p50, color: 'bg-blue-500' },
                    { label: 'Haut (75%)', value: monteCarlo.percentiles.p75, color: 'bg-green-400' },
                    { label: 'Optimiste (95%)', value: monteCarlo.percentiles.p95, color: 'bg-green-600' },
                  ].map((p) => (
                    <div key={p.label} className="flex items-center gap-3">
                      <span className="text-xs w-28 text-muted-foreground">{p.label}</span>
                      <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden relative">
                        <div
                          className={`h-full ${p.color} rounded-full absolute`}
                          style={{
                            width: `${Math.min(100, Math.max(2, Math.abs(p.value)))}%`,
                            left: p.value < 0 ? `${Math.max(0, 50 + p.value / 2)}%` : '50%',
                          }}
                        />
                        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-foreground/30" />
                      </div>
                      <span className={`text-xs font-mono w-16 text-right ${p.value >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {p.value > 0 ? '+' : ''}{p.value.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
                {/* Stats */}
                <div className="grid grid-cols-3 gap-3 pt-2 border-t">
                  <div className="text-center">
                    <div className="text-lg font-bold">{monteCarlo.expected_return > 0 ? '+' : ''}{monteCarlo.expected_return.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Rendement moyen</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-green-500">{monteCarlo.prob_positive.toFixed(0)}%</div>
                    <div className="text-xs text-muted-foreground">Prob. gain</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-red-500">{monteCarlo.prob_loss_10.toFixed(0)}%</div>
                    <div className="text-xs text-muted-foreground">Prob. perte &gt;10%</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
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
                <div className="space-y-2">
                  {Object.entries(optimization.weights)
                    .sort((a, b) => b[1] - a[1])
                    .filter(([_, w]) => w >= 0.5)
                    .map(([symbol, weight]) => {
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

      {/* Stress Test + Beta */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Stress Test */}
        {stressTest && stressTest.scenarios.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-orange-500" />
                Stress Tests
              </CardTitle>
              <CardDescription>
                Impact de scénarios de crise historiques sur votre portefeuille
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {stressTest.scenarios.map((scenario) => (
                  <div key={scenario.name} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium">{scenario.name}</span>
                      <span className="text-sm font-bold text-red-500">
                        {scenario.total_loss_pct.toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">{scenario.description}</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-red-500 rounded-full"
                          style={{ width: `${Math.min(100, Math.abs(scenario.total_loss_pct))}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-red-500 w-24 text-right">
                        {formatCurrency(scenario.total_loss)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
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
                          <TooltipTrigger>
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
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="name" width={60} tick={{ fontSize: 12 }} />
                <RechartsTooltip formatter={(value: number) => `${value}%`} />
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
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => `${v}%`} />
                <RechartsTooltip formatter={(value: number) => `${value}%`} />
                <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Correlation Matrix */}
      {correlation && correlation.symbols.length > 1 && (() => {
        // Build color for correlation value: blue (negative) → gray (0) → red (positive)
        const corrColor = (v: number, isDiag: boolean) => {
          if (isDiag) return 'bg-muted'
          const abs = Math.abs(v)
          if (v > 0.01) return `rgba(239, 68, 68, ${Math.min(abs * 0.85, 0.85)})`   // red
          if (v < -0.01) return `rgba(59, 130, 246, ${Math.min(abs * 0.85, 0.85)})`  // blue
          return 'rgba(148, 163, 184, 0.1)'
        }
        const corrTextColor = (v: number) => {
          const abs = Math.abs(v)
          if (abs > 0.55) return 'text-white'
          return ''
        }
        const corrLabel = (v: number) => {
          if (v >= 0.7) return 'Forte +'
          if (v >= 0.4) return 'Modérée +'
          if (v <= -0.5) return 'Inverse'
          if (v <= -0.3) return 'Faible -'
          return ''
        }

        return (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Matrice de corrélation
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <HelpCircle className="h-4 w-4 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      <p className="text-xs">+1 = parfaitement corrélés, 0 = indépendants, -1 = inversement corrélés. Basé sur 60j de rendements journaliers.</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </CardTitle>
              <CardDescription>Comment vos actifs évoluent ensemble</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Heatmap grid */}
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b">
                      <th className="p-2 bg-muted/50 sticky left-0 z-10"></th>
                      {correlation.symbols.map((sym) => (
                        <th key={sym} className="p-2 text-center font-semibold text-xs bg-muted/50 min-w-[52px]">
                          {sym}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {correlation.symbols.map((sym1, i) => (
                      <tr key={sym1} className="border-b last:border-b-0">
                        <td className="p-2 font-semibold text-xs bg-muted/50 sticky left-0 z-10">{sym1}</td>
                        {correlation.symbols.map((sym2, j) => {
                          const value = correlation.matrix[i]?.[j] ?? 0
                          const isDiag = i === j
                          return (
                            <TooltipProvider key={`${sym1}-${sym2}`}>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <td
                                    className={`p-0 text-center transition-opacity hover:opacity-80 ${isDiag ? 'bg-muted' : ''}`}
                                    style={!isDiag ? { backgroundColor: corrColor(value, false) } : undefined}
                                  >
                                    <div className={`py-2 px-1 text-xs font-mono font-medium ${corrTextColor(value)} ${isDiag ? 'text-muted-foreground' : ''}`}>
                                      {isDiag ? '—' : value.toFixed(2)}
                                    </div>
                                  </td>
                                </TooltipTrigger>
                                {!isDiag && (
                                  <TooltipContent>
                                    <p className="text-xs font-medium">{sym1} / {sym2}</p>
                                    <p className="text-xs text-muted-foreground">
                                      Corrélation: {value.toFixed(3)}
                                      {corrLabel(value) && ` (${corrLabel(value)})`}
                                    </p>
                                  </TooltipContent>
                                )}
                              </Tooltip>
                            </TooltipProvider>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Color scale legend */}
              <div className="flex items-center justify-center gap-2">
                <span className="text-xs text-muted-foreground">-1</span>
                <div className="flex h-3 w-48 rounded-full overflow-hidden">
                  <div className="flex-1" style={{ background: 'rgba(59, 130, 246, 0.85)' }} />
                  <div className="flex-1" style={{ background: 'rgba(59, 130, 246, 0.45)' }} />
                  <div className="flex-1" style={{ background: 'rgba(148, 163, 184, 0.2)' }} />
                  <div className="flex-1" style={{ background: 'rgba(239, 68, 68, 0.45)' }} />
                  <div className="flex-1" style={{ background: 'rgba(239, 68, 68, 0.85)' }} />
                </div>
                <span className="text-xs text-muted-foreground">+1</span>
              </div>

              {/* Notable pairs */}
              {(correlation.strongly_correlated.length > 0 || correlation.negatively_correlated.length > 0) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {correlation.strongly_correlated.length > 0 && (
                    <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                      <p className="text-xs font-semibold text-red-500 mb-2">Fortement corrélés (risque de concentration)</p>
                      <div className="space-y-1.5">
                        {correlation.strongly_correlated.slice(0, 4).map(([s1, s2, v]) => (
                          <div key={`${s1}-${s2}`} className="flex items-center justify-between">
                            <span className="text-xs">{s1} — {s2}</span>
                            <span className="text-xs font-mono font-semibold text-red-500">{typeof v === 'number' ? v.toFixed(2) : v}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {correlation.negatively_correlated.length > 0 && (
                    <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                      <p className="text-xs font-semibold text-blue-500 mb-2">Corrélation inverse (bonne diversification)</p>
                      <div className="space-y-1.5">
                        {correlation.negatively_correlated.slice(0, 4).map(([s1, s2, v]) => (
                          <div key={`${s1}-${s2}`} className="flex items-center justify-between">
                            <span className="text-xs">{s1} — {s2}</span>
                            <span className="text-xs font-mono font-semibold text-blue-500">{typeof v === 'number' ? v.toFixed(2) : v}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })()}

      {/* Recommendations */}
      {diversification && diversification.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
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
