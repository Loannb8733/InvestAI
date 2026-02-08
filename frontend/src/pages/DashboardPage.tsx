import { useState, useRef, lazy, Suspense, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '@/components/OnboardingWizard'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
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
import { dashboardApi } from '@/services/api'
import AllocationChart from '@/components/charts/AllocationChart'
import PerformanceChart from '@/components/charts/PerformanceChart'
import {
  LineChart,
  Line,
  XAxis as RXAxis,
  YAxis as RYAxis,
  CartesianGrid as RCartesianGrid,
  Tooltip as RTooltip,
  ResponsiveContainer,
  Legend as RLegend,
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Loader2,
  Banknote,
  Plus,
  Bell,
  Calendar,
  Clock,
  Activity,
  BarChart3,
  ArrowRightLeft,
  ChevronRight,
  Zap,
  AlertTriangle,
  ShieldAlert,
  Info,
  Target,
  TrendingDown as TrendDown,
  Scale,
  Printer,
  Settings2,
  GripVertical,
  Eye,
  EyeOff,
  RotateCcw,
  X,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { useExportPdf } from '@/hooks/useExportPdf'
import { useDashboardLayout, WIDGET_LABELS, type WidgetId } from '@/hooks/useDashboardLayout'

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

interface PnLBreakdown {
  realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
  total_fees: number
  net_pnl: number
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
  portfolios_count: number
  assets_count: number
  allocation: Array<{ type: string; value: number; percentage: number }>
  asset_allocation: AssetAllocation[]
  top_performers: Array<{ symbol: string; name: string; asset_type: string; gain_loss_percent: number; current_value: number }>
  worst_performers: Array<{ symbol: string; name: string; asset_type: string; gain_loss_percent: number; current_value: number }>
  historical_data: Array<{ date: string; value: number; is_estimated?: boolean }>
  is_data_estimated: boolean
  recent_transactions: RecentTransaction[]
  active_alerts: ActiveAlert[]
  upcoming_events: UpcomingEvent[]
  index_comparison: IndexComparison[]
  advanced_metrics: AdvancedMetrics
  last_updated: string
}

// ============== Constants ==============

const PERIOD_OPTIONS = [
  { label: '7j', value: 7 },
  { label: '30j', value: 30 },
  { label: '90j', value: 90 },
  { label: '1an', value: 365 },
]

const transactionTypeLabels: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Staking',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
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
        <Button variant="ghost" size="sm" onClick={onClose} className="h-6 w-6 p-0">
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
  const [selectedPeriod, setSelectedPeriod] = useState(30)
  const { showOnboarding, markDone } = useOnboarding()
  const [onboardingVisible, setOnboardingVisible] = useState(showOnboarding)
  const { exportToPdf } = useExportPdf()
  const { visibleWidgets, hiddenWidgets, toggleWidget, moveWidget, resetLayout } = useDashboardLayout()
  const [showCustomize, setShowCustomize] = useState(false)
  const [showBenchmarks, setShowBenchmarks] = useState(false)
  const dragIndexRef = useRef<number | null>(null)

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
    queryKey: ['dashboard', selectedPeriod],
    queryFn: () => dashboardApi.getMetrics(selectedPeriod),
    refetchInterval: 60000,
  })

  const { data: benchmarks } = useQuery<Array<{ name: string; symbol: string; data: Array<{ date: string; value: number }> }>>({
    queryKey: ['benchmarks', selectedPeriod],
    queryFn: () => dashboardApi.getBenchmarks(selectedPeriod),
    enabled: showBenchmarks,
  })

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

  const netGainLoss = metrics?.net_gain_loss ?? metrics?.total_gain_loss ?? 0
  const isPositive = netGainLoss >= 0
  const isDailyPositive = (metrics?.daily_change ?? 0) >= 0

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

  const { advanced_metrics } = metrics
  const { risk_metrics, concentration, stress_tests, pnl_breakdown } = advanced_metrics

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
          <p className="text-sm text-muted-foreground mt-1">
            Dernière mise à jour : {new Date(metrics.last_updated).toLocaleString('fr-FR')}
          </p>
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
      {(metrics.is_data_estimated || concentration.is_concentrated) && (
        <div className="space-y-2">
          {metrics.is_data_estimated && (
            <Alert variant="default" className="border-yellow-500/50 bg-yellow-500/10">
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
              <AlertDescription className="text-yellow-600 dark:text-yellow-400">
                Les données historiques sont estimées. Les valeurs réelles seront enregistrées à partir d'aujourd'hui.
              </AlertDescription>
            </Alert>
          )}
          {concentration.is_concentrated && (
            <Alert variant="destructive" className="border-red-500/50 bg-red-500/10">
              <ShieldAlert className="h-4 w-4" />
              <AlertDescription>
                Alerte concentration : {concentration.top_asset} représente {concentration.top_concentration}% de votre portefeuille.
                Envisagez de diversifier vos investissements.
              </AlertDescription>
            </Alert>
          )}
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
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Patrimoine Total</CardTitle>
                        <Wallet className="h-4 w-4 text-muted-foreground" />
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold">{formatCurrency(metrics.total_value)}</div>
                        <p className="text-xs text-muted-foreground">{metrics.assets_count} actifs</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Capital Net</CardTitle>
                        <Banknote className="h-4 w-4 text-muted-foreground" />
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold">{formatCurrency(metrics.net_capital ?? metrics.total_invested)}</div>
                        <p className="text-xs text-muted-foreground">{formatCurrency(metrics.total_invested)} investi au total</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Plus-value Nette</CardTitle>
                        {isPositive ? <TrendingUp className="h-4 w-4 text-green-500" /> : <TrendingDown className="h-4 w-4 text-red-500" />}
                      </CardHeader>
                      <CardContent>
                        <div className={`text-2xl font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(netGainLoss)}</div>
                        <p className={`text-xs ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{formatPercent(metrics.net_gain_loss_percent ?? metrics.total_gain_loss_percent)}</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Variation 24h</CardTitle>
                        {isDailyPositive ? <ArrowUpRight className="h-4 w-4 text-green-500" /> : <ArrowDownRight className="h-4 w-4 text-red-500" />}
                      </CardHeader>
                      <CardContent>
                        <div className={`text-2xl font-bold ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(metrics.daily_change)}</div>
                        <p className={`text-xs ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{formatPercent(metrics.daily_change_percent)}</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Portefeuilles</CardTitle>
                        <PieChart className="h-4 w-4 text-muted-foreground" />
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold">{metrics.portfolios_count}</div>
                        <p className="text-xs text-muted-foreground">portefeuille{metrics.portfolios_count > 1 ? 's' : ''} actif{metrics.portfolios_count > 1 ? 's' : ''}</p>
                      </CardContent>
                    </Card>
                  </div>
                )
              case 'pnl':
                return (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2"><Scale className="h-4 w-4" />Répartition des Plus/Moins-values</CardTitle>
                      <CardDescription>Distinction entre gains réalisés et latents (fiscalité)</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div>
                          <MetricTooltip content="Profits/pertes sur les positions actuellement détenues. Non imposable tant que non vendu."><p className="text-xs text-muted-foreground">P&L Latent</p></MetricTooltip>
                          <p className={`text-lg font-bold ${pnl_breakdown.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(pnl_breakdown.unrealized_pnl)}</p>
                        </div>
                        <div>
                          <MetricTooltip content="Profits/pertes sur les actifs vendus. Soumis à imposition."><p className="text-xs text-muted-foreground">P&L Réalisé</p></MetricTooltip>
                          <p className={`text-lg font-bold ${pnl_breakdown.realized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(pnl_breakdown.realized_pnl)}</p>
                        </div>
                        <div>
                          <MetricTooltip content="Total des frais de transaction payés."><p className="text-xs text-muted-foreground">Total Frais</p></MetricTooltip>
                          <p className="text-lg font-bold text-orange-500">-{formatCurrency(pnl_breakdown.total_fees)}</p>
                        </div>
                        <div>
                          <MetricTooltip content="P&L total (latent + réalisé)."><p className="text-xs text-muted-foreground">P&L Total</p></MetricTooltip>
                          <p className={`text-lg font-bold ${pnl_breakdown.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(pnl_breakdown.total_pnl)}</p>
                        </div>
                        <div>
                          <MetricTooltip content="P&L net après déduction des frais."><p className="text-xs text-muted-foreground">P&L Net</p></MetricTooltip>
                          <p className={`text-lg font-bold ${pnl_breakdown.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(pnl_breakdown.net_pnl)}</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )
              case 'risk':
                return (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content="Mesure de la dispersion des rendements. Plus la volatilité est élevée, plus le risque est important."><p className="text-sm text-muted-foreground">Volatilité</p></MetricTooltip>
                            <p className="text-xl font-bold">{risk_metrics.volatility.toFixed(1)}%</p>
                            <p className="text-xs text-muted-foreground">annualisée</p>
                          </div>
                          <Activity className="h-8 w-8 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content="Rendement ajusté au risque. >1 = bon, >2 = très bon, <0 = mauvais"><p className="text-sm text-muted-foreground">Ratio de Sharpe</p></MetricTooltip>
                            <p className={`text-xl font-bold ${risk_metrics.sharpe_ratio >= 1 ? 'text-green-500' : risk_metrics.sharpe_ratio >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>{risk_metrics.sharpe_ratio.toFixed(2)}</p>
                            <p className="text-xs text-muted-foreground">{risk_metrics.sharpe_ratio >= 1 ? 'Bon' : risk_metrics.sharpe_ratio >= 0 ? 'Moyen' : 'Faible'}</p>
                          </div>
                          <Zap className="h-8 w-8 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content="Perte maximale historique entre un pic et un creux. Mesure le pire scénario passé."><p className="text-sm text-muted-foreground">Max Drawdown</p></MetricTooltip>
                            <p className="text-xl font-bold text-red-500">-{risk_metrics.max_drawdown.max_drawdown_percent.toFixed(1)}%</p>
                            <p className="text-xs text-muted-foreground">pire baisse</p>
                          </div>
                          <TrendDown className="h-8 w-8 text-red-500" />
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <MetricTooltip content={`Perte potentielle maximale avec ${(risk_metrics.var_95.confidence_level * 100).toFixed(0)}% de confiance sur 1 jour.`}><p className="text-sm text-muted-foreground">VaR 95%</p></MetricTooltip>
                            <p className="text-xl font-bold text-orange-500">{formatCurrency(risk_metrics.var_95.var_amount)}</p>
                            <p className="text-xs text-muted-foreground">soit {risk_metrics.var_95.var_percent.toFixed(1)}%</p>
                          </div>
                          <ShieldAlert className="h-8 w-8 text-orange-500" />
                        </div>
                      </CardContent>
                    </Card>
                  </div>
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
                                <span className="text-sm font-medium text-red-500">-{formatCurrency(test.potential_loss)}</span>
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
                      <CardTitle className="text-sm font-medium">Comparaison avec les indices (24h)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex gap-6 flex-wrap">
                        {metrics.index_comparison.map((index) => (
                          <div key={index.symbol} className="flex items-center gap-3">
                            <AssetIconCompact symbol={index.symbol} assetType="crypto" size={32} />
                            <div>
                              <p className="text-sm font-medium">{index.name}</p>
                              <p className={`text-sm ${index.change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{index.change_percent >= 0 ? '+' : ''}{index.change_percent.toFixed(2)}%</p>
                            </div>
                            <p className="text-sm text-muted-foreground ml-2">{formatCurrency(index.price)}</p>
                          </div>
                        ))}
                        <div className="flex items-center gap-3 border-l pl-6 ml-2">
                          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center"><Wallet className="h-4 w-4 text-primary" /></div>
                          <div>
                            <p className="text-sm font-medium">Votre portefeuille</p>
                            <p className={`text-sm ${metrics.daily_change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{metrics.daily_change_percent >= 0 ? '+' : ''}{metrics.daily_change_percent.toFixed(2)}%</p>
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
                          Évolution du patrimoine ({selectedPeriod}j)
                          {metrics.is_data_estimated && (<Badge variant="outline" className="text-yellow-600 border-yellow-500">Estimé</Badge>)}
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
                        <CardTitle>Répartition par actif</CardTitle>
                        <Button variant="ghost" size="sm" onClick={() => navigate('/analytics')}>Voir plus<ChevronRight className="h-4 w-4 ml-1" /></Button>
                      </CardHeader>
                      <CardContent>
                        {metrics.asset_allocation.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.asset_allocation.slice(0, 6).map((asset) => (
                              <div key={asset.symbol} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={asset.symbol} name={asset.name} assetType={asset.asset_type} size={32} />
                                  <div>
                                    <p className="font-medium text-sm">{asset.symbol}</p>
                                    <p className="text-xs text-muted-foreground">{formatCurrency(asset.value)}</p>
                                  </div>
                                </div>
                                <div className="text-right">
                                  <p className="font-medium text-sm">{asset.percentage.toFixed(1)}%</p>
                                  <p className={`text-xs ${asset.gain_loss_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatPercent(asset.gain_loss_percent)}</p>
                                </div>
                              </div>
                            ))}
                            {metrics.asset_allocation.length > 6 && (<p className="text-xs text-muted-foreground text-center pt-2">+{metrics.asset_allocation.length - 6} autres actifs</p>)}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-8">Aucun actif</p>)}
                      </CardContent>
                    </Card>
                  </div>
                  {showBenchmarks && benchmarks && benchmarks.length > 0 && (() => {
                    const BENCH_COLORS = ['#3b82f6', '#f59e0b', '#8b5cf6', '#22c55e']
                    // Merge all series into one dataset keyed by date
                    const dateMap: Record<string, Record<string, number>> = {}
                    benchmarks.forEach((series) => {
                      series.data.forEach((p) => {
                        if (!dateMap[p.date]) dateMap[p.date] = {}
                        dateMap[p.date][series.symbol] = p.value
                      })
                    })
                    const chartData = Object.entries(dateMap)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([date, vals]) => ({ date: date.slice(5), ...vals }))

                    return (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium">Performance comparee (base 100)</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ResponsiveContainer width="100%" height={250}>
                            <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                              <RCartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
                              <RXAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                              <RYAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
                              <RTooltip contentStyle={{ fontSize: 12 }} />
                              <RLegend verticalAlign="top" height={30} wrapperStyle={{ fontSize: 12 }} />
                              {benchmarks.map((series, i) => (
                                <Line key={series.symbol} type="monotone" dataKey={series.symbol} name={series.name} stroke={BENCH_COLORS[i % BENCH_COLORS.length]} strokeWidth={2} dot={false} />
                              ))}
                            </LineChart>
                          </ResponsiveContainer>
                        </CardContent>
                      </Card>
                    )
                  })()}
                  </div>
                )
              case 'allocation-transactions-alerts':
                return (
                  <div className="grid gap-4 lg:grid-cols-3">
                    <Card className="lg:col-span-1">
                      <CardHeader><CardTitle>Répartition par classe</CardTitle></CardHeader>
                      <CardContent><AllocationChart data={metrics.allocation} /></CardContent>
                    </Card>
                    <Card className="lg:col-span-1">
                      <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="flex items-center gap-2"><Clock className="h-4 w-4" />Transactions récentes</CardTitle>
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
                                    {tx.transaction_type.includes('sell') || tx.transaction_type.includes('out') ? '-' : '+'}{formatCurrency(tx.total)}
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
                                      {event.amount && (<p className="text-sm font-medium text-green-500">+{formatCurrency(event.amount)}</p>)}
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
                        <CardTitle className="text-green-500 flex items-center gap-2"><TrendingUp className="h-5 w-5" />Meilleures performances</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {metrics.top_performers.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.top_performers.map((item, index) => (
                              <div key={`top-${item.symbol}-${index}`} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                                  <div><p className="font-medium text-sm">{item.symbol}</p><p className="text-xs text-muted-foreground">{formatCurrency(item.current_value)}</p></div>
                                </div>
                                <div className="flex items-center text-green-500"><ArrowUpRight className="h-4 w-4 mr-1" /><span className="font-medium">{formatPercent(item.gain_loss_percent)}</span></div>
                              </div>
                            ))}
                          </div>
                        ) : (<p className="text-muted-foreground text-center py-4">Aucun actif en gain</p>)}
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-red-500 flex items-center gap-2"><TrendingDown className="h-5 w-5" />Moins bonnes performances</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {metrics.worst_performers.length > 0 ? (
                          <div className="space-y-3">
                            {metrics.worst_performers.map((item, index) => (
                              <div key={`worst-${item.symbol}-${index}`} className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                                  <div><p className="font-medium text-sm">{item.symbol}</p><p className="text-xs text-muted-foreground">{formatCurrency(item.current_value)}</p></div>
                                </div>
                                <div className="flex items-center text-red-500"><ArrowDownRight className="h-4 w-4 mr-1" /><span className="font-medium">{formatPercent(item.gain_loss_percent)}</span></div>
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
