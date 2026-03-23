import { useState, useRef, useMemo, lazy, Suspense, type ReactNode } from 'react'
import type { PnLBreakdown } from '@/types'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '@/components/OnboardingWizard'
import { useRealtimePrices } from '@/hooks/useRealtimePrices'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { MIN_DISPLAY_VALUE } from '@/lib/constants'
import { dashboardApi, crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useAuthStore } from '@/stores/authStore'
import AllocationChart from '@/components/charts/AllocationChart'
import CryptoClassChart from '@/components/charts/CryptoClassChart'
import PlatformPieChart from '@/components/charts/PlatformPieChart'
import SecurityBadge from '@/components/charts/SecurityBadge'
import PerformanceChart from '@/components/charts/PerformanceChart'
import CurrencyExposureChart from '@/components/charts/CurrencyExposureChart'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Loader2,
  Plus,
  Bell,
  Calendar,
  Clock,
  BarChart3,
  ArrowRightLeft,
  ChevronRight,
  ShieldAlert,
  Info,
  Target,
  Printer,
  Settings2,
  GripVertical,
  Eye,
  EyeOff,
  RotateCcw,
  X,
  Radio,
  Landmark,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { useExportPdf } from '@/hooks/useExportPdf'
import { useDashboardLayout, WIDGET_LABELS, type WidgetId } from '@/hooks/useDashboardLayout'
import DashboardMetricsRow from '@/components/dashboard/DashboardMetricsRow'
import DashboardPnlCard from '@/components/dashboard/DashboardPnlCard'
import DashboardRiskCards from '@/components/dashboard/DashboardRiskCards'
import DashboardBenchmarkChart from '@/components/dashboard/DashboardBenchmarkChart'
import DashboardMunitionsCard from '@/components/dashboard/DashboardMunitionsCard'
import DashboardEarnCard from '@/components/dashboard/DashboardEarnCard'
import StalePriceBadge from '@/components/dashboard/StalePriceBadge'

// ============== Interfaces ==============

interface MaxDrawdown {
  max_drawdown_percent: number
  peak_date?: string
  trough_date?: string
  peak_value?: number
  trough_value?: number
}

interface ValueAtRisk {
  var_percent: number
  var_amount: number
  confidence_level: number
}

interface ConcentrationMetrics {
  hhi: number
  interpretation: string
  is_concentrated: boolean
  top_asset?: string
  top_concentration?: number
}

interface StressTest {
  scenario_name: string
  current_value: number
  stressed_value: number
  potential_loss: number
  potential_loss_percent: number
}

interface RiskMetrics {
  volatility: number
  sharpe_ratio: number
  max_drawdown: MaxDrawdown
  var_95: ValueAtRisk
  beta?: number
  alpha?: number
}

interface AdvancedMetrics {
  roi_annualized: number
  risk_metrics: RiskMetrics
  concentration: ConcentrationMetrics
  stress_tests: StressTest[]
  pnl_breakdown: PnLBreakdown
}

interface AssetAllocation {
  symbol: string
  name?: string
  asset_type: string
  value: number
  percentage: number
  gain_loss_percent: number
  avg_buy_price?: number
  staked_quantity?: number
}

interface EarnAsset {
  symbol: string
  staked_quantity: number
  current_value: number
}

interface EarnSummary {
  total_staked_value: number
  total_rewards: number
  apr?: number
  assets: EarnAsset[]
}

interface RecentTransaction {
  id: string
  symbol: string
  asset_type: string
  transaction_type: string
  quantity: number
  price: number
  total: number
  executed_at: string
}

interface ActiveAlert {
  id: string
  name: string
  symbol?: string
  condition: string
  threshold: number
  current_price?: number
}

interface UpcomingEvent {
  id: string
  title: string
  event_type: string
  event_date: string
  amount?: number
}

interface IndexComparison {
  name: string
  symbol: string
  change_percent: number
  price: number
}

interface DashboardMetrics {
  total_value: number
  total_invested: number
  net_capital: number
  total_gain_loss: number
  total_gain_loss_percent: number
  net_gain_loss: number
  net_gain_loss_percent: number
  daily_change: number
  daily_change_percent: number
  period_change?: number
  period_change_percent?: number
  portfolios_count: number
  assets_count: number
  allocation: Array<{ type: string; value: number; percentage: number }>
  asset_allocation: AssetAllocation[]
  top_performers: Array<{ symbol: string; name: string; asset_type: string; gain_loss_percent: number; current_value: number }>
  worst_performers: Array<{ symbol: string; name: string; asset_type: string; gain_loss_percent: number; current_value: number }>
  historical_data: Array<{ date: string; value: number }>
  is_data_estimated: boolean
  recent_transactions: RecentTransaction[]
  active_alerts: ActiveAlert[]
  upcoming_events: UpcomingEvent[]
  index_comparison: IndexComparison[]
  advanced_metrics: AdvancedMetrics
  available_liquidity?: number
  earn_summary?: EarnSummary
  currency_exposure?: Array<{ currency: string; value: number; percentage: number }>
  total_dividend_income?: number
  total_return?: number
  period_days?: number
  period_label?: string
  forex_stale?: boolean
  last_updated: string
}

// ============== Constants ==============

const PERIOD_OPTIONS = [
  { label: '24h', value: 1 },
  { label: '7j', value: 7 },
  { label: '30j', value: 30 },
  { label: '90j', value: 90 },
  { label: '1an', value: 365 },
  { label: 'Tout', value: 0 },
]

const transactionTypeLabels: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Reward',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
  staking: 'Staking',
  unstaking: 'Unstaking',
}

const eventTypeLabels: Record<string, string> = {
  dividend: 'Dividende',
  rent: 'Loyer',
  interest: 'Intérêt',
  payment_due: 'Échéance',
  rebalance: 'Rééquilibrage',
  tax_deadline: 'Impôts',
  reminder: 'Rappel',
  other: 'Autre',
}

// ============== Helper Component for Tooltips ==============

function MetricTooltip({ children, content }: { children: React.ReactNode; content: string }) {
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help inline-flex items-center gap-1">
            {children}
            <Info className="h-3 w-3 text-muted-foreground" />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-sm">{content}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// ============== Drag & Drop Widget ==============

function DraggableWidget({
  id,
  index,
  children,
  onDragStart,
  onDragOver,
  onDrop,
}: {
  id: WidgetId
  index: number
  children: ReactNode
  onDragStart: (index: number) => void
  onDragOver: (e: React.DragEvent, index: number) => void
  onDrop: (index: number) => void
}) {
  return (
    <div
      draggable
      onDragStart={() => onDragStart(index)}
      onDragOver={(e) => onDragOver(e, index)}
      onDrop={() => onDrop(index)}
      className="group relative"
      data-widget={id}
    >
      <div className="absolute -left-6 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-60 transition-opacity cursor-grab active:cursor-grabbing print:hidden">
        <GripVertical className="h-5 w-5 text-muted-foreground" />
      </div>
      {children}
    </div>
  )
}

function CustomizePanel({
  visibleWidgets,
  hiddenWidgets,
  onToggle,
  onReset,
  onClose,
}: {
  visibleWidgets: readonly WidgetId[]
  hiddenWidgets: readonly WidgetId[]
  onToggle: (id: WidgetId) => void
  onReset: () => void
  onClose: () => void
}) {
  const allIds = [...visibleWidgets, ...hiddenWidgets]
  return (
    <Card className="absolute right-0 top-12 z-50 w-72 shadow-lg">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Personnaliser le dashboard</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose} className="h-6 w-6 p-0" aria-label="Fermer le panneau de personnalisation">
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {allIds.map((id) => {
          const isHidden = hiddenWidgets.includes(id)
          return (
            <button
              key={id}
              onClick={() => onToggle(id)}
              className="flex items-center justify-between w-full px-2 py-1.5 rounded hover:bg-muted transition-colors text-sm"
            >
              <span className={isHidden ? 'text-muted-foreground' : ''}>{WIDGET_LABELS[id]}</span>
              {isHidden ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-green-500" />}
            </button>
          )
        })}
        <div className="pt-2 border-t">
          <Button variant="ghost" size="sm" onClick={onReset} className="w-full text-xs">
            <RotateCcw className="h-3 w-3 mr-1" />
            Réinitialiser
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ============== Main Component ==============

const OnboardingWizard = lazy(() => import('@/components/OnboardingWizard'))

export default function DashboardPage() {
  const navigate = useNavigate()
  const [selectedPeriod, setSelectedPeriod] = useState(0)
  const { showOnboarding, markDone } = useOnboarding()
  const [onboardingVisible, setOnboardingVisible] = useState(showOnboarding)
  const { exportToPdf } = useExportPdf()
  const pageVisible = usePageVisibility()
  const { visibleWidgets, hiddenWidgets, toggleWidget, moveWidget, resetLayout } = useDashboardLayout()
  const [showCustomize, setShowCustomize] = useState(false)
  const [showBenchmarks, setShowBenchmarks] = useState(false)
  const [privacyMode, setPrivacyMode] = useState(() => localStorage.getItem('investai-privacy') === 'true')
  const dragIndexRef = useRef<number | null>(null)
  const currency = useAuthStore((s) => s.user?.preferredCurrency || 'EUR')

  const handleDragStart = (index: number) => { dragIndexRef.current = index }
  const handleDragOver = (e: React.DragEvent, _index: number) => { e.preventDefault() }
  const handleDrop = (toIndex: number) => {
    if (dragIndexRef.current !== null && dragIndexRef.current !== toIndex) {
      moveWidget(dragIndexRef.current, toIndex)
    }
    dragIndexRef.current = null
  }

  const {
    data: metrics,
    isLoading,
    error,
    refetch,
  } = useQuery<DashboardMetrics>({
    queryKey: [...queryKeys.dashboard.metrics(selectedPeriod), currency],
    queryFn: () => dashboardApi.getMetrics(selectedPeriod),
    refetchInterval: pageVisible ? 60000 : false,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })

  const { data: cfDashboard } = useQuery<import('@/types/crowdfunding').CrowdfundingDashboard>({
    queryKey: ['crowdfunding', 'dashboard'],
    queryFn: () => crowdfundingApi.getDashboard(),
    staleTime: 60_000,
  })

  const { data: benchmarks } = useQuery<Array<{ name: string; symbol: string; data: Array<{ date: string; value: number }> }>>({
    queryKey: [...queryKeys.dashboard.benchmarks(selectedPeriod), currency],
    queryFn: () => dashboardApi.getBenchmarks(selectedPeriod),
    enabled: showBenchmarks,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })

  // Real-time price updates via WebSocket
  const portfolioSymbols = useMemo(() => {
    if (!metrics?.asset_allocation) return []
    return metrics.asset_allocation.map((a) => a.symbol)
  }, [metrics?.asset_allocation])

  const { prices: livePrices, connected: wsConnected } = useRealtimePrices(portfolioSymbols)

  // Helper: get live price for a symbol, falling back to the static value
  const getLivePrice = (symbol: string, fallbackValue: number): number => {
    const live = livePrices[symbol.toUpperCase()]
    return live ? live.price : fallbackValue
  }

  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <p className="text-destructive">Erreur lors du chargement des données</p>
        <Button onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Réessayer
        </Button>
      </div>
    )
  }

  // P&L: always use net_gain_loss (total_value - net_capital), never fall back to total_gain_loss
  // total_gain_loss uses all-time invested as denominator which is wrong for users with sells
  const netGainLoss = metrics?.net_gain_loss ?? 0
  const isPositive = netGainLoss >= 0
  // Use period change for all periods except 24h (selectedPeriod=1)
  // selectedPeriod=0 ("Tout") needs period_change (true P&L vs cost basis)
  // Do NOT fall back to daily_change for non-24h periods — it's from a different data source
  const variationChange = selectedPeriod === 1
    ? (metrics?.daily_change ?? 0)
    : (metrics?.period_change ?? 0)
  const variationPercent = selectedPeriod === 1
    ? (metrics?.daily_change_percent ?? 0)
    : (metrics?.period_change_percent ?? 0)
  const isDailyPositive = variationChange >= 0

  // Empty state
  if (!metrics || metrics.assets_count === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Tableau de bord</h1>
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <Wallet className="h-16 w-16 mx-auto text-muted-foreground" />
              <h2 className="text-xl font-semibold">Bienvenue sur InvestAI !</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Commencez par créer un portefeuille et ajouter vos premiers actifs
                pour voir apparaître vos métriques et analyses.
              </p>
              <Button onClick={() => navigate('/portfolio')}>
                Créer mon premier portefeuille
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const advanced_metrics = metrics.advanced_metrics ?? ({} as NonNullable<typeof metrics.advanced_metrics>)
  const { risk_metrics, stress_tests = [], pnl_breakdown } = advanced_metrics
  const concentration = advanced_metrics.concentration ?? { is_concentrated: false, hhi: 0, interpretation: 'N/A', top_asset: '', top_concentration: 0 }
  // Always derive periodLabel from local selectedPeriod (not API) so it updates instantly on click
  const periodLabel = selectedPeriod === 0 ? 'Depuis le début' : selectedPeriod === 1 ? '24h' : selectedPeriod === 365 ? '1 an' : `${selectedPeriod}j`

  return (
    <div className="space-y-6">
      {/* Onboarding wizard */}
      {onboardingVisible && (
        <Suspense fallback={null}>
          <OnboardingWizard onComplete={() => { markDone(); setOnboardingVisible(false) }} />
        </Suspense>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Tableau de bord</h1>
          <div className="flex items-center gap-3 mt-1">
            <p className="text-sm text-muted-foreground">
              Dernière mise à jour : {new Date(metrics.last_updated).toLocaleString('fr-FR')}
            </p>
            {wsConnected && (
              <Badge variant="outline" className="text-green-600 border-green-500/50 bg-green-500/10 gap-1 text-xs">
                <Radio className="h-3 w-3 animate-pulse" />
                Live
              </Badge>
            )}
            <StalePriceBadge wsConnected={wsConnected} forexStale={metrics.forex_stale} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex bg-muted rounded-lg p-1">
            {PERIOD_OPTIONS.map((period) => (
              <Button
                key={period.value}
                variant={selectedPeriod === period.value ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setSelectedPeriod(period.value)}
                className="px-3"
              >
                {period.label}
              </Button>
            ))}
          </div>
          <div className="flex gap-2 relative">
            <Button variant="outline" size="sm" onClick={() => setShowCustomize((v) => !v)}>
              <Settings2 className="h-4 w-4 mr-2" />
              Personnaliser
            </Button>
            {showCustomize && (
              <CustomizePanel
                visibleWidgets={visibleWidgets}
                hiddenWidgets={hiddenWidgets}
                onToggle={toggleWidget}
                onReset={resetLayout}
                onClose={() => setShowCustomize(false)}
              />
            )}
            <Button variant="outline" size="sm" onClick={() => setPrivacyMode((v) => { const next = !v; localStorage.setItem('investai-privacy', String(next)); return next })} title={privacyMode ? 'Afficher les montants' : 'Masquer les montants'}>
              {privacyMode ? <EyeOff className="h-4 w-4 mr-2" /> : <Eye className="h-4 w-4 mr-2" />}
              {privacyMode ? 'Afficher' : 'Masquer'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportToPdf('Dashboard InvestAI')} data-no-print>
              <Printer className="h-4 w-4 mr-2" />
              PDF
            </Button>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Actualiser
            </Button>
          </div>
        </div>
      </div>

      {/* Alerts Section */}
      {concentration.is_concentrated && (
        <div className="space-y-2">
          <Alert variant="destructive" className="border-red-500/50 bg-red-500/10">
            <ShieldAlert className="h-4 w-4" />
            <AlertDescription>
              Alerte concentration : {concentration.top_asset} représente {concentration.top_concentration}% de votre portefeuille.
              Envisagez de diversifier vos investissements.
            </AlertDescription>
          </Alert>
        </div>
      )}

      {/* Quick Actions */}
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => navigate('/portfolio')}>
          <Plus className="h-4 w-4 mr-1" />
          Ajouter un actif
        </Button>
        <Button variant="outline" size="sm" onClick={() => navigate('/transactions')}>
          <ArrowRightLeft className="h-4 w-4 mr-1" />
          Nouvelle transaction
        </Button>
        <Button variant="outline" size="sm" onClick={() => navigate('/alerts')}>
          <Bell className="h-4 w-4 mr-1" />
          Créer une alerte
        </Button>
      </div>

      {/* Dynamic Widgets */}
      <div className="space-y-6 pl-6">
        {visibleWidgets.map((widgetId, idx) => {
          const content = (() => {
            switch (widgetId) {
              case 'metrics':
                return (
                  <DashboardMetricsRow
                    totalValue={metrics.total_value}
                    assetsCount={metrics.assets_count}
                    netCapital={metrics.net_capital}
                    totalInvested={metrics.total_invested}
                    netGainLoss={netGainLoss}
                    netGainLossPercent={metrics.net_gain_loss_percent}
                    isPositive={isPositive}
                    dailyChange={variationChange}
                    dailyChangePercent={variationPercent}
                    isDailyPositive={isDailyPositive}
                    portfoliosCount={metrics.portfolios_count}
                    selectedPeriod={selectedPeriod}
                    availableLiquidity={metrics.available_liquidity}
                    privacyMode={privacyMode}
                  />
                )
              case 'munitions':
                return <DashboardMunitionsCard availableLiquidity={metrics.available_liquidity} totalValue={metrics.total_value} privacyMode={privacyMode} />
              case 'earn':
                if (!metrics.earn_summary) return null
                return <DashboardEarnCard earnSummary={metrics.earn_summary} privacyMode={privacyMode} />
              case 'crowdfunding':
                if (!cfDashboard || cfDashboard.active_count === 0 && cfDashboard.completed_count === 0) return null
                return (
                  <Card className="cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => navigate('/crowdfunding')}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Landmark className="h-4 w-4 text-blue-400" />
                        Crowdfunding
                        <Badge variant="outline" className="ml-auto text-[10px]">
                          {cfDashboard.active_count} actif{cfDashboard.active_count > 1 ? 's' : ''}
                        </Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground">Total investi</p>
                          <p className="text-lg font-bold">{pc(cfDashboard.total_invested)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Rendement projeté/an</p>
                          <p className="text-lg font-bold text-green-500">+{pc(cfDashboard.projected_annual_interest)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Taux moyen</p>
                          <p className="text-lg font-bold">{cfDashboard.weighted_average_rate.toFixed(1)}%</p>
                        </div>
                      </div>
                      {cfDashboard.next_maturity && (
                        <p className="text-xs text-muted-foreground mt-2">
                          Prochaine échéance : {new Date(cfDashboard.next_maturity).toLocaleDateString('fr-FR')}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )
              case 'pnl':
                return (
                  // P&L breakdown is always all-time (realized gains are cumulative)
                  // Show "Depuis le début" regardless of selected period to avoid misleading labels
                  <DashboardPnlCard pnlBreakdown={pnl_breakdown} periodLabel="Depuis le début" privacyMode={privacyMode} totalDividendIncome={metrics.total_dividend_income} totalReturn={metrics.total_return} />
                )
              case 'risk':
                return (
                  <DashboardRiskCards riskMetrics={risk_metrics} periodLabel={periodLabel} privacyMode={privacyMode} />
                )
              case 'roi-concentration':
                return (
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content="Retour sur investissement projeté sur une année complète."><p className="text-sm text-muted-foreground">ROI Annualisé</p></MetricTooltip>
                            <p className={`text-xl font-bold ${advanced_metrics.roi_annualized >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatPercent(advanced_metrics.roi_annualized)}</p>
                          </div>
                          <BarChart3 className="h-8 w-8 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content="Indice de Herfindahl-Hirschman. Mesure la concentration du portefeuille. <1500 = diversifié, 1500-2500 = modéré, >2500 = concentré"><p className="text-sm text-muted-foreground">Concentration (HHI)</p></MetricTooltip>
                            <p className={`text-xl font-bold ${concentration.is_concentrated ? 'text-red-500' : 'text-green-500'}`}>{concentration.hhi.toFixed(0)}</p>
                            <p className="text-xs text-muted-foreground">{concentration.interpretation}</p>
                          </div>
                          <Target className="h-8 w-8 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-6">
                        <div>
                          <MetricTooltip content="Simulation de l'impact d'une correction de marché sur votre portefeuille."><p className="text-sm text-muted-foreground mb-2">Stress Tests</p></MetricTooltip>
                          <div className="space-y-2">
                            {stress_tests.map((test) => (
                              <div key={test.scenario_name} className="flex justify-between items-center">
                                <span className="text-sm">{test.scenario_name}</span>
                                <span className="text-sm font-medium text-red-500">{pc(test.potential_loss)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )
              case 'indices':
                return metrics.index_comparison.length > 0 ? (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">Comparaison avec les indices ({selectedPeriod === 0 ? 'Tout' : selectedPeriod === 1 ? '24h' : selectedPeriod === 365 ? '1an' : `${selectedPeriod}j`})</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex gap-6 flex-wrap">
                        {metrics.index_comparison.map((idx) => {
                          const liveIndexPrice = getLivePrice(idx.symbol, idx.price)
                          return (
                          <div key={idx.symbol} className="flex items-center gap-3">
                            <AssetIconCompact symbol={idx.symbol} assetType="crypto" size={32} />
                            <div>
                              <div className="flex items-center gap-1.5">
                                <p className="text-sm font-medium">{idx.name}</p>
                                {livePrices[idx.symbol.toUpperCase()] && <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />}
                              </div>
                              <p className={`text-sm ${idx.change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{idx.change_percent >= 0 ? '▲ +' : '▼ '}{idx.change_percent.toFixed(2)}%</p>
                            </div>
                            <p className="text-sm text-muted-foreground ml-2">{pc(liveIndexPrice)}</p>
                          </div>)
                        })}
                        <div className="flex items-center gap-3 border-l pl-6 ml-2">
                          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center"><Wallet className="h-4 w-4 text-primary" /></div>
                          <div>
                            <p className="text-sm font-medium">Votre portefeuille</p>
                            <p className={`text-sm ${variationPercent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{variationPercent >= 0 ? '▲ +' : '▼ '}{variationPercent.toFixed(2)}%</p>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : null
              case 'charts':
                return (
                  <div className="space-y-4">
                  <div className="grid gap-4 lg:grid-cols-2">
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          Évolution du patrimoine ({selectedPeriod === 0 ? 'Tout' : selectedPeriod === 365 ? '1an' : `${selectedPeriod}j`})
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <PerformanceChart data={metrics.historical_data} period={selectedPeriod} color={isPositive ? '#22c55e' : '#ef4444'} />
                        <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={() => setShowBenchmarks((v) => !v)}>
                          {showBenchmarks ? 'Masquer' : 'Comparer aux benchmarks'}
                        </Button>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle>Répartition par actif <span className="text-xs font-normal text-muted-foreground">({periodLabel})</span></CardTitle>
                        <Button variant="ghost" size="sm" onClick={() => navigate('/analytics')}>Voir plus<ChevronRight className="h-4 w-4 ml-1" /></Button>
                      </CardHeader>
                      <CardContent>
                        {metrics.asset_allocation.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.asset_allocation.filter((a) => a.value >= MIN_DISPLAY_VALUE).slice(0, 6).map((asset, i) => (
                              <div key={`${asset.symbol}-${i}`} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={asset.symbol} name={asset.name} assetType={asset.asset_type} size={32} />
                                  <div>
                                    <div className="flex items-center gap-1.5">
                                      <p className="font-medium text-sm">{asset.symbol}</p>
                                      {/* Live indicator removed: asset.value is server-computed, not updated with WS prices */}
                                    </div>
                                    <p className="text-xs text-muted-foreground">{pc(asset.value)}{asset.staked_quantity != null && asset.staked_quantity > 0 && <span className="ml-1 text-purple-500">(dont {asset.staked_quantity.toFixed(2)} en Staking)</span>}</p>
                                  </div>
                                </div>
                                <div className="text-right">
                                  <p className="font-medium text-sm">{asset.percentage.toFixed(1)}%</p>
                                  <p className={`text-xs ${asset.gain_loss_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{asset.gain_loss_percent >= 0 ? '▲ +' : '▼ -'}{formatPercent(Math.abs(asset.gain_loss_percent))}</p>
                                </div>
                              </div>
                            ))}
                            {metrics.asset_allocation.length > 6 && (<p className="text-xs text-muted-foreground text-center pt-2">+{metrics.asset_allocation.length - 6} autres actifs</p>)}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-8">Aucun actif</p>)}
                      </CardContent>
                    </Card>
                  </div>
                  {showBenchmarks && benchmarks && benchmarks.length > 0 && (
                    <DashboardBenchmarkChart benchmarks={benchmarks} />
                  )}
                  </div>
                )
              case 'currency-exposure':
                if (!metrics.currency_exposure || metrics.currency_exposure.length === 0) return null
                return (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Exposition Devises
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CurrencyExposureChart data={metrics.currency_exposure} />
                    </CardContent>
                  </Card>
                )
              case 'allocation-transactions-alerts':
                return (
                  <div className="grid gap-4 lg:grid-cols-3">
                    <Card>
                      <CardHeader><CardTitle>Répartition par classe</CardTitle></CardHeader>
                      <CardContent><AllocationChart data={metrics.allocation} /></CardContent>
                    </Card>
                    <Card>
                      <CardHeader><CardTitle>Crypto par catégorie</CardTitle></CardHeader>
                      <CardContent><CryptoClassChart assets={metrics.asset_allocation} /></CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle>Répartition par plateforme</CardTitle>
                        <SecurityBadge />
                      </CardHeader>
                      <CardContent><PlatformPieChart onPlatformClick={(p) => { if (p) navigate(`/transactions?platform=${encodeURIComponent(p)}`) }} /></CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="flex items-center gap-2"><Clock className="h-4 w-4" />Transactions récentes <span className="text-xs font-normal text-muted-foreground">({periodLabel})</span></CardTitle>
                        <Button variant="ghost" size="sm" onClick={() => navigate('/transactions')}>Voir tout<ChevronRight className="h-4 w-4 ml-1" /></Button>
                      </CardHeader>
                      <CardContent>
                        {metrics.recent_transactions.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.recent_transactions.map((tx) => (
                              <div key={tx.id} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={tx.symbol} assetType={tx.asset_type} size={28} />
                                  <div>
                                    <p className="text-sm font-medium">{tx.symbol}</p>
                                    <p className="text-xs text-muted-foreground">{transactionTypeLabels[tx.transaction_type] || tx.transaction_type}</p>
                                  </div>
                                </div>
                                <div className="text-right">
                                  <p className={`text-sm font-medium ${tx.transaction_type.includes('sell') || tx.transaction_type.includes('out') ? 'text-red-500' : 'text-green-500'}`}>
                                    {tx.transaction_type.includes('sell') || tx.transaction_type.includes('out') ? '-' : '+'}{pc(tx.total)}
                                  </p>
                                  <p className="text-xs text-muted-foreground">{new Date(tx.executed_at).toLocaleDateString('fr-FR')}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-8">Aucune transaction</p>)}
                      </CardContent>
                    </Card>
                    <Card className="lg:col-span-1">
                      <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4" />Alertes & Événements</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-4">
                          {metrics.active_alerts.length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-muted-foreground mb-2">ALERTES ACTIVES</p>
                              <div className="space-y-2">
                                {metrics.active_alerts.slice(0, 3).map((alert) => (
                                  <div key={alert.id} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                                    <div className="flex items-center gap-2"><Bell className="h-3 w-3 text-orange-500" /><span className="text-sm">{alert.name}</span></div>
                                    {alert.symbol && <span className="text-xs text-muted-foreground">{alert.symbol}</span>}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {metrics.upcoming_events.length > 0 && (
                            <div>
                              <p className="text-xs font-medium text-muted-foreground mb-2">ÉVÉNEMENTS À VENIR</p>
                              <div className="space-y-2">
                                {metrics.upcoming_events.slice(0, 3).map((event) => (
                                  <div key={event.id} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                                    <div className="flex items-center gap-2">
                                      <Calendar className="h-3 w-3 text-blue-500" />
                                      <div><span className="text-sm">{event.title}</span><p className="text-xs text-muted-foreground">{eventTypeLabels[event.event_type] || event.event_type}</p></div>
                                    </div>
                                    <div className="text-right">
                                      {event.amount && (<p className="text-sm font-medium text-green-500">+{pc(event.amount)}</p>)}
                                      <p className="text-xs text-muted-foreground">{new Date(event.event_date).toLocaleDateString('fr-FR')}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {metrics.active_alerts.length === 0 && metrics.upcoming_events.length === 0 && (
                            <div className="text-center py-4">
                              <p className="text-muted-foreground text-sm">Aucune alerte ou événement</p>
                              <div className="flex gap-2 justify-center mt-3">
                                <Button variant="outline" size="sm" onClick={() => navigate('/alerts')}><Bell className="h-3 w-3 mr-1" />Alertes</Button>
                                <Button variant="outline" size="sm" onClick={() => navigate('/calendar')}><Calendar className="h-3 w-3 mr-1" />Calendrier</Button>
                              </div>
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )
              case 'performers':
                return (
                  <div className="grid gap-4 md:grid-cols-2">
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-green-500 flex items-center gap-2"><TrendingUp className="h-5 w-5" />Meilleures performances <span className="text-xs font-normal text-muted-foreground">({periodLabel})</span></CardTitle>
                      </CardHeader>
                      <CardContent>
                        {metrics.top_performers.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.top_performers.map((item, index) => (
                              <div key={`top-${item.symbol}-${index}`} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                                  <div>
                                    <div className="flex items-center gap-1.5"><p className="font-medium text-sm">{item.symbol}</p>{livePrices[item.symbol.toUpperCase()] && <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />}</div>
                                    <p className="text-xs text-muted-foreground">{pc(item.current_value)}</p>
                                  </div>
                                </div>
                                <div className="flex items-center text-green-500"><ArrowUpRight className="h-4 w-4 mr-1" /><span className="font-medium">+{privacyMode ? '••••' : formatPercent(Math.abs(item.gain_loss_percent))}</span></div>
                              </div>
                            ))}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-4">Aucun actif en gain</p>)}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-red-500 flex items-center gap-2"><TrendingDown className="h-5 w-5" />Moins bonnes performances <span className="text-xs font-normal text-muted-foreground">({periodLabel})</span></CardTitle>
                      </CardHeader>
                      <CardContent>
                        {metrics.worst_performers.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.worst_performers.map((item, index) => (
                              <div key={`worst-${item.symbol}-${index}`} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                                  <div>
                                    <div className="flex items-center gap-1.5"><p className="font-medium text-sm">{item.symbol}</p>{livePrices[item.symbol.toUpperCase()] && <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />}</div>
                                    <p className="text-xs text-muted-foreground">{pc(item.current_value)}</p>
                                  </div>
                                </div>
                                <div className="flex items-center text-red-500"><ArrowDownRight className="h-4 w-4 mr-1" /><span className="font-medium">-{privacyMode ? '••••' : formatPercent(Math.abs(item.gain_loss_percent))}</span></div>
                              </div>
                            ))}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-4">Aucun actif en perte</p>)}
                      </CardContent>
                    </Card>
                  </div>
                )
              default:
                return null
            }
          })()
          if (!content) return null
          return (
            <DraggableWidget key={widgetId} id={widgetId} index={idx} onDragStart={handleDragStart} onDragOver={handleDragOver} onDrop={handleDrop}>
              {content}
            </DraggableWidget>
          )
        })}
      </div>
    </div>
  )
}
