import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { formatCurrency } from '@/lib/utils'
import { smartInsightsApi } from '@/services/api'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Gauge,
  Loader2,
  RefreshCw,
  Shield,
  Target,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface Insight {
  category: string
  severity: string
  title: string
  message: string
  metric_name?: string
  current_value?: number
  target_value?: number
  potential_improvement?: string
  actions: Array<{
    type: string
    symbol: string
    amount_eur?: number
    reason?: string
  }>
}

interface RebalancingOrder {
  symbol: string
  name: string
  action: string
  current_weight: number
  target_weight: number
  current_value_eur: number
  target_value_eur: number
  amount_eur: number
  reason: string
}

interface AnomalyImpact {
  symbol: string
  anomaly_type: string
  severity: string
  description: string
  price_change_percent: number
  position_value_eur: number
  impact_eur: number
  detected_at: string
}

interface MetricsSummary {
  sharpe_ratio: number
  sortino_ratio: number
  volatility: number
  var_95: number
  max_drawdown: number
  hhi: number
  total_value: number
}

interface IndicatorSignal {
  name: string
  value: number
  signal: string
  strength: number
  description: string
}

interface RegimeResult {
  symbol: string
  probabilities: Record<string, number>
  dominant_regime: string
  confidence: number
  signals: IndicatorSignal[]
  description: string
}

interface MarketRegime {
  market: RegimeResult
  per_asset: RegimeResult[]
  generated_at: string
}

interface PortfolioHealth {
  overall_score: number
  overall_status: string
  insights: Insight[]
  rebalancing_orders: RebalancingOrder[]
  anomaly_impacts: AnomalyImpact[]
  metrics_summary: MetricsSummary
  market_regime?: MarketRegime | null
  generated_at: string
}

export default function SmartInsightsPage() {
  const [days, setDays] = useState(30)

  const { data, isLoading, refetch, isFetching } = useQuery<PortfolioHealth>({
    queryKey: ['smart-insights-health', days],
    queryFn: () => smartInsightsApi.getHealth(days),
    staleTime: 5 * 60 * 1000,
  })

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-500'
    if (score >= 60) return 'text-yellow-500'
    if (score >= 40) return 'text-orange-500'
    return 'text-red-500'
  }

  const getScoreBg = (score: number) => {
    if (score >= 80) return 'bg-green-500/10 border-green-500/20'
    if (score >= 60) return 'bg-yellow-500/10 border-yellow-500/20'
    if (score >= 40) return 'bg-orange-500/10 border-orange-500/20'
    return 'bg-red-500/10 border-red-500/20'
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-500/10 text-red-500 border-red-500/20'
      case 'warning': return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20'
      case 'info': return 'bg-blue-500/10 text-blue-500 border-blue-500/20'
      default: return 'bg-muted text-muted-foreground'
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'performance': return <TrendingUp className="h-4 w-4" />
      case 'risk': return <Shield className="h-4 w-4" />
      case 'diversification': return <BarChart3 className="h-4 w-4" />
      case 'anomaly': return <AlertTriangle className="h-4 w-4" />
      default: return <Activity className="h-4 w-4" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Brain className="h-8 w-8 text-primary" />
            Smart Insights
          </h1>
          <p className="text-muted-foreground">
            Analyse IA de votre portefeuille avec recommandations personnalisees
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 jours</SelectItem>
              <SelectItem value="30">30 jours</SelectItem>
              <SelectItem value="90">90 jours</SelectItem>
              <SelectItem value="365">1 an</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : data ? (
        <>
          {/* Score global + Metriques */}
          <div className="grid gap-4 lg:grid-cols-4">
            {/* Score */}
            <Card className={`border-2 ${getScoreBg(data.overall_score)}`}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Score global</p>
                    <div className={`text-5xl font-bold ${getScoreColor(data.overall_score)}`}>
                      {data.overall_score}
                    </div>
                    <p className="text-sm mt-1 capitalize">{data.overall_status}</p>
                  </div>
                  <Gauge className={`h-16 w-16 ${getScoreColor(data.overall_score)}`} />
                </div>
              </CardContent>
            </Card>

            {/* Sharpe */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Ratio de Sharpe</p>
                    <div className={`text-3xl font-bold ${(data.metrics_summary.sharpe_ratio ?? 0) >= 1 ? 'text-green-500' : (data.metrics_summary.sharpe_ratio ?? 0) >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>
                      {(data.metrics_summary.sharpe_ratio ?? 0).toFixed(2)}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {(data.metrics_summary.sharpe_ratio ?? 0) >= 1 ? 'Bon' : (data.metrics_summary.sharpe_ratio ?? 0) >= 0.5 ? 'Correct' : 'A ameliorer'}
                    </p>
                  </div>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Target className="h-8 w-8 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Rendement ajuste au risque. Objectif: &gt;1</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </CardContent>
            </Card>

            {/* VaR */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">VaR 95%</p>
                    <div className="text-3xl font-bold text-red-500">
                      {formatCurrency(data.metrics_summary.var_95 ?? 0)}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Perte max/jour (5% prob.)
                    </p>
                  </div>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Shield className="h-8 w-8 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Perte maximale attendue sur 1 jour avec 95% de confiance</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </CardContent>
            </Card>

            {/* Diversification */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Concentration (HHI)</p>
                    <div className={`text-3xl font-bold ${(data.metrics_summary.hhi ?? 0) < 0.15 ? 'text-green-500' : (data.metrics_summary.hhi ?? 0) < 0.25 ? 'text-yellow-500' : 'text-red-500'}`}>
                      {((data.metrics_summary.hhi ?? 0) * 100).toFixed(0)}%
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {(data.metrics_summary.hhi ?? 0) < 0.15 ? 'Bien diversifie' : (data.metrics_summary.hhi ?? 0) < 0.25 ? 'Moderement concentre' : 'Tres concentre'}
                    </p>
                  </div>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <BarChart3 className="h-8 w-8 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Indice Herfindahl-Hirschman. Plus bas = plus diversifie</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Market Regime */}
          {data.market_regime && (
            <MarketRegimeCard regime={data.market_regime} />
          )}

          {/* Insights */}
          {data.insights.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="h-5 w-5 text-yellow-500" />
                  Recommandations IA
                </CardTitle>
                <CardDescription>
                  Actions suggérees pour améliorer votre portefeuille
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {data.insights.map((insight, idx) => (
                    <div key={idx} className={`p-4 rounded-lg border ${getSeverityColor(insight.severity)}`}>
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">{getCategoryIcon(insight.category)}</div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-semibold">{insight.title}</h4>
                            <Badge variant="outline" className="text-xs capitalize">
                              {insight.category}
                            </Badge>
                          </div>
                          <p className="text-sm">{insight.message}</p>

                          {insight.current_value != null && insight.target_value != null && (
                            <div className="mt-2 flex items-center gap-4 text-sm">
                              <span>Actuel: <strong>{(insight.current_value ?? 0).toFixed(2)}</strong></span>
                              <ArrowUpRight className="h-4 w-4" />
                              <span>Objectif: <strong>{(insight.target_value ?? 0).toFixed(2)}</strong></span>
                            </div>
                          )}

                          {insight.potential_improvement && (
                            <p className="mt-2 text-sm text-green-500">
                              <CheckCircle2 className="h-4 w-4 inline mr-1" />
                              {insight.potential_improvement}
                            </p>
                          )}

                          {insight.actions.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {insight.actions.map((action, aidx) => (
                                <Badge key={aidx} variant="secondary" className="text-xs">
                                  {action.type === 'buy' ? (
                                    <ArrowUpRight className="h-3 w-3 mr-1 text-green-500" />
                                  ) : action.type === 'sell' ? (
                                    <ArrowDownRight className="h-3 w-3 mr-1 text-red-500" />
                                  ) : null}
                                  {action.type.toUpperCase()} {action.symbol}
                                  {action.amount_eur && ` (${formatCurrency(action.amount_eur)})`}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Rebalancing suggestions */}
          {data.rebalancing_orders.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <RefreshCw className="h-5 w-5 text-blue-500" />
                  Suggestions de reequilibrage
                </CardTitle>
                <CardDescription>
                  Ordres suggeres pour optimiser le ratio de Sharpe (MPT)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">Actif</th>
                        <th className="text-center p-2">Action</th>
                        <th className="text-right p-2">Poids actuel</th>
                        <th className="text-right p-2">Poids cible</th>
                        <th className="text-right p-2">Montant</th>
                        <th className="text-left p-2">Raison</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.rebalancing_orders.map((order, idx) => (
                        <tr key={idx} className="border-b last:border-b-0">
                          <td className="p-2">
                            <div className="font-medium">{order.symbol}</div>
                            <div className="text-xs text-muted-foreground">{order.name}</div>
                          </td>
                          <td className="p-2 text-center">
                            <Badge variant={order.action === 'buy' ? 'default' : 'destructive'}>
                              {order.action === 'buy' ? (
                                <ArrowUpRight className="h-3 w-3 mr-1" />
                              ) : (
                                <ArrowDownRight className="h-3 w-3 mr-1" />
                              )}
                              {order.action === 'buy' ? 'Acheter' : 'Vendre'}
                            </Badge>
                          </td>
                          <td className="p-2 text-right">{((order.current_weight ?? 0) * 100).toFixed(1)}%</td>
                          <td className="p-2 text-right">{((order.target_weight ?? 0) * 100).toFixed(1)}%</td>
                          <td className="p-2 text-right font-mono">
                            <span className={order.action === 'buy' ? 'text-green-500' : 'text-red-500'}>
                              {order.action === 'buy' ? '+' : '-'}{formatCurrency(Math.abs(order.amount_eur ?? 0))}
                            </span>
                          </td>
                          <td className="p-2 text-xs text-muted-foreground max-w-[200px]">{order.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Anomalies with impact */}
          {data.anomaly_impacts.length > 0 && (
            <Card className="border-orange-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-orange-500" />
                  Anomalies detectees
                </CardTitle>
                <CardDescription>
                  Mouvements inhabituels sur vos positions avec impact en EUR
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {data.anomaly_impacts.map((anomaly, idx) => (
                    <div key={idx} className="p-4 rounded-lg bg-muted/50 border">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{anomaly.symbol}</span>
                          <Badge variant="outline" className={
                            anomaly.severity === 'high' ? 'border-red-500 text-red-500' :
                            anomaly.severity === 'medium' ? 'border-yellow-500 text-yellow-500' :
                            'border-blue-500 text-blue-500'
                          }>
                            {anomaly.severity}
                          </Badge>
                          <Badge variant="secondary" className="text-xs">
                            {anomaly.anomaly_type}
                          </Badge>
                        </div>
                        <div className="text-right">
                          <div className={`font-mono font-bold ${(anomaly.impact_eur ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {(anomaly.impact_eur ?? 0) >= 0 ? '+' : ''}{formatCurrency(anomaly.impact_eur ?? 0)}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {(anomaly.price_change_percent ?? 0) >= 0 ? '+' : ''}{(anomaly.price_change_percent ?? 0).toFixed(1)}%
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Position: {formatCurrency(anomaly.position_value_eur ?? 0)} |
                        Detecte: {new Date(anomaly.detected_at).toLocaleDateString('fr-FR')}
                      </p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Empty states */}
          {data.insights.length === 0 && data.rebalancing_orders.length === 0 && data.anomaly_impacts.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center">
                <CheckCircle2 className="h-16 w-16 mx-auto text-green-500 mb-4" />
                <h3 className="text-xl font-semibold">Votre portefeuille est en bonne sante !</h3>
                <p className="text-muted-foreground mt-2">
                  Aucune recommandation ou anomalie detectee pour le moment.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Footer */}
          <p className="text-xs text-muted-foreground text-center">
            Analyse generee le {new Date(data.generated_at).toLocaleString('fr-FR')}
          </p>
        </>
      ) : (
        <Card>
          <CardContent className="py-12 text-center">
            <AlertTriangle className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
            <p className="text-muted-foreground">Impossible de charger les donnees</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}


// ──────────────────────────────────────────────────────
// Market Regime Card
// ──────────────────────────────────────────────────────

const REGIME_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  bearish: { label: 'Bearish', color: '#ef4444', bg: 'bg-red-500/10', icon: <TrendingDown className="h-5 w-5 text-red-500" /> },
  bottom: { label: 'Bottom', color: '#f97316', bg: 'bg-orange-500/10', icon: <ArrowUpRight className="h-5 w-5 text-orange-500" /> },
  bullish: { label: 'Bullish', color: '#22c55e', bg: 'bg-green-500/10', icon: <TrendingUp className="h-5 w-5 text-green-500" /> },
  top: { label: 'Top', color: '#a855f7', bg: 'bg-purple-500/10', icon: <ArrowDownRight className="h-5 w-5 text-purple-500" /> },
}

const SIGNAL_COLORS: Record<string, string> = {
  bearish: 'border-red-500/40 text-red-500',
  bottom: 'border-orange-500/40 text-orange-500',
  bullish: 'border-green-500/40 text-green-500',
  top: 'border-purple-500/40 text-purple-500',
}

function RegimeBar({ probabilities }: { probabilities: Record<string, number> }) {
  return (
    <div className="flex w-full h-8 rounded-lg overflow-hidden border">
      {(['bearish', 'bottom', 'bullish', 'top'] as const).map((phase) => {
        const pct = (probabilities[phase] ?? 0) * 100
        if (pct < 1) return null
        const cfg = REGIME_CONFIG[phase]
        return (
          <TooltipProvider key={phase}>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className="flex items-center justify-center text-xs font-bold text-white transition-all"
                  style={{ width: `${pct}%`, backgroundColor: cfg.color, minWidth: pct > 5 ? '2rem' : '0' }}
                >
                  {pct >= 10 && `${pct.toFixed(0)}%`}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>{cfg.label}: {pct.toFixed(1)}%</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )
      })}
    </div>
  )
}

function MarketRegimeCard({ regime }: { regime: MarketRegime }) {
  const market = regime.market
  const dominant = REGIME_CONFIG[market.dominant_regime] || REGIME_CONFIG.bullish

  return (
    <Card className={`border-2 ${dominant.bg}`}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          Regime de Marche
        </CardTitle>
        <CardDescription>
          Analyse basee sur 7 indicateurs techniques (BTC comme proxy)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Dominant regime */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            {dominant.icon}
            <span className="text-2xl font-bold" style={{ color: dominant.color }}>
              {dominant.label}
            </span>
          </div>
          <Badge variant="outline" className="text-xs">
            Confiance: {(market.confidence * 100).toFixed(0)}%
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{market.description}</p>

        {/* Probability bar */}
        <div>
          <div className="flex justify-between text-xs text-muted-foreground mb-1">
            {(['bearish', 'bottom', 'bullish', 'top'] as const).map((phase) => (
              <span key={phase} className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: REGIME_CONFIG[phase].color }} />
                {REGIME_CONFIG[phase].label}
              </span>
            ))}
          </div>
          <RegimeBar probabilities={market.probabilities} />
        </div>

        {/* Indicator signals */}
        {market.signals.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Signaux des indicateurs</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {market.signals.map((sig, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
                  <Badge variant="outline" className={`text-xs ${SIGNAL_COLORS[sig.signal] || ''}`}>
                    {REGIME_CONFIG[sig.signal]?.label || sig.signal}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{sig.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{sig.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per-asset regimes */}
        {regime.per_asset.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Par actif</p>
            <div className="space-y-2">
              {regime.per_asset.map((asset, idx) => {
                const assetCfg = REGIME_CONFIG[asset.dominant_regime] || REGIME_CONFIG.bullish
                return (
                  <div key={idx} className="flex items-center gap-3">
                    <span className="text-sm font-mono w-16 text-right">{asset.symbol}</span>
                    <div className="flex-1">
                      <div className="flex w-full h-4 rounded overflow-hidden">
                        {(['bearish', 'bottom', 'bullish', 'top'] as const).map((phase) => {
                          const pct = (asset.probabilities[phase] ?? 0) * 100
                          if (pct < 1) return null
                          return (
                            <div
                              key={phase}
                              className="transition-all"
                              style={{ width: `${pct}%`, backgroundColor: REGIME_CONFIG[phase].color }}
                            />
                          )
                        })}
                      </div>
                    </div>
                    <Badge variant="outline" className={`text-xs w-20 justify-center ${SIGNAL_COLORS[asset.dominant_regime] || ''}`}>
                      {assetCfg.label}
                    </Badge>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
