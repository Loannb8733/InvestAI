import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCurrency } from '@/lib/utils'
import { predictionsApi } from '@/services/api'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Brain,
  Loader2,
  ArrowUp,
  ArrowDown,
  Minus,
  Zap,
  ShieldAlert,
  Target,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  BarChart3,
  Bell,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts'

interface PredictionPoint {
  date: string
  price: number
  confidence_low: number
  confidence_high: number
}

interface PortfolioPrediction {
  symbol: string
  name: string
  asset_type: string
  current_price: number
  predicted_price: number
  change_percent: number
  trend: string
  trend_strength: number
  recommendation: string
  model_used: string
  predictions: PredictionPoint[]
  support_level: number
  resistance_level: number
  accuracy: number
  consensus_score: number
  models_agree: boolean
  models_detail?: { name: string; weight_pct: number; trend: string; mape?: number }[]
  explanations?: { feature_name: string; importance: number; direction: string }[]
}

interface PortfolioPredictionSummary {
  total_current_value: number
  total_predicted_value: number
  expected_change_percent: number
  overall_sentiment: string
  bullish_assets: number
  bearish_assets: number
  neutral_assets: number
  days_ahead: number
}

interface Anomaly {
  symbol: string
  is_anomaly: boolean
  anomaly_type: string | null
  severity: string
  description: string
  detected_at: string
  price_change_percent: number
}

interface Signal {
  type: string
  message: string
  action: string
}

interface MarketSentiment {
  overall_sentiment: string
  sentiment_score: number
  fear_greed_index: number
  market_phase: string
  signals: Signal[]
}

interface WhatIfResult {
  current_value: number
  simulated_value: number
  impact_percent: number
  per_asset: Array<{
    symbol: string
    name: string
    current_value: number
    simulated_value: number
    change_percent: number
    impact: number
  }>
}

// ── Fear & Greed Arc Gauge (large) ──────────────────────────────────
const FearGreedGauge = ({ value }: { value: number }) => {
  const clampedValue = Math.max(0, Math.min(100, value))
  const angle = Math.max(1, (clampedValue / 100) * 180) // min 1° to avoid zero-length arc
  const radians = (angle * Math.PI) / 180
  const x = 60 - 45 * Math.cos(radians)
  const y = 55 - 45 * Math.sin(radians)

  // Gradient colors
  const getColor = (v: number) => {
    if (v >= 75) return '#22c55e'
    if (v >= 55) return '#84cc16'
    if (v >= 45) return '#eab308'
    if (v >= 25) return '#f97316'
    return '#ef4444'
  }
  const getLabel = (v: number) => {
    if (v >= 75) return 'Extrême avidité'
    if (v >= 55) return 'Avidité'
    if (v >= 45) return 'Neutre'
    if (v >= 25) return 'Peur'
    return 'Extrême peur'
  }
  const color = getColor(clampedValue)

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="85" viewBox="0 0 120 70">
        {/* Background arc */}
        <path
          d="M 15 55 A 45 45 0 0 1 105 55"
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          className="text-muted/20"
        />
        {/* Value arc */}
        <path
          d={`M 15 55 A 45 45 0 ${angle > 180 ? 1 : 0} 1 ${x} ${y}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* Value text */}
        <text x="60" y="50" textAnchor="middle" fill={color} fontSize="22" fontWeight="bold">
          {Math.round(clampedValue)}
        </text>
      </svg>
      <span className="text-sm font-medium" style={{ color }}>{getLabel(clampedValue)}</span>
    </div>
  )
}

// ── Combined Score (accuracy + consensus) ───────────────────────────
const CombinedScore = ({ accuracy, consensus }: { accuracy: number; consensus: number }) => {
  const score = Math.round((accuracy * 0.6 + consensus * 0.4))
  const color = score >= 70 ? 'bg-green-500' : score >= 45 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = score >= 70 ? 'text-green-500' : score >= 45 ? 'text-yellow-500' : 'text-red-500'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 cursor-help">
            <div className="w-14 h-2 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
            </div>
            <span className={`text-xs font-bold ${textColor}`}>{score}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">Fiabilité {accuracy.toFixed(0)}% · Consensus {consensus.toFixed(0)}%</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// ── Variation bar (visual % change) ─────────────────────────────────
const VariationBar = ({ percent }: { percent: number }) => {
  const clamped = Math.max(-20, Math.min(20, percent))
  const width = Math.abs(clamped) / 20 * 50 // max 50% of bar
  const isPositive = percent >= 0

  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 rounded-full bg-muted relative overflow-hidden">
        <div
          className={`absolute h-full rounded-full ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
          style={{
            width: `${width}%`,
            left: isPositive ? '50%' : `${50 - width}%`,
          }}
        />
        <div className="absolute left-1/2 top-0 w-px h-full bg-muted-foreground/30" />
      </div>
      <span className={`text-sm font-bold tabular-nums ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
        {isPositive ? '+' : ''}{percent.toFixed(1)}%
      </span>
    </div>
  )
}

export default function PredictionsPage() {
  const [daysAhead, setDaysAhead] = useState(7)
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null)
  const [whatIfSymbol, setWhatIfSymbol] = useState<string>('')
  const [whatIfChange, setWhatIfChange] = useState<number>(0)
  const [whatIfResult, setWhatIfResult] = useState<WhatIfResult | null>(null)
  const [whatIfLoading, setWhatIfLoading] = useState(false)

  const { data: portfolioPredictions, isLoading: loadingPredictions } = useQuery({
    queryKey: ['portfolio-predictions', daysAhead],
    queryFn: () => predictionsApi.getPortfolioPredictions(daysAhead),
  })

  const { data: anomalies } = useQuery<Anomaly[]>({
    queryKey: ['anomalies'],
    queryFn: predictionsApi.getAnomalies,
  })

  const { data: sentiment, isLoading: loadingSentiment } = useQuery<MarketSentiment>({
    queryKey: ['market-sentiment'],
    queryFn: predictionsApi.getMarketSentiment,
  })

  const summary = portfolioPredictions?.summary as PortfolioPredictionSummary | undefined
  const predictions = portfolioPredictions?.predictions as PortfolioPrediction[] | undefined

  // Initialize whatIfSymbol when predictions load (via useMemo to avoid setState during render)
  const effectiveWhatIfSymbol = whatIfSymbol || (predictions && predictions.length > 0 ? predictions[0].symbol : '')

  // ── Unified alerts: merge predictive alerts + market signals ──
  const unifiedAlerts = useMemo(() => {
    const items: Array<{
      symbol?: string
      type: string
      message: string
      severity: 'high' | 'medium' | 'low'
      icon: string
      source: string
    }> = []

    // From predictions data
    if (predictions) {
      for (const pred of predictions) {
        if (pred.predicted_price < pred.support_level && pred.support_level > 0) {
          items.push({
            symbol: pred.symbol,
            type: 'support_break',
            message: `${pred.symbol} pourrait casser son support à ${formatCurrency(pred.support_level)}`,
            severity: 'high',
            icon: 'shield',
            source: 'prediction',
          })
        }
        if (pred.predicted_price > pred.resistance_level && pred.resistance_level > 0) {
          items.push({
            symbol: pred.symbol,
            type: 'breakout',
            message: `${pred.symbol} pourrait franchir sa résistance à ${formatCurrency(pred.resistance_level)}`,
            severity: 'medium',
            icon: 'trending_up',
            source: 'prediction',
          })
        }
        if (pred.trend_strength > 70) {
          items.push({
            symbol: pred.symbol,
            type: 'strong_trend',
            message: `Tendance ${pred.trend === 'bullish' ? 'haussière' : 'baissière'} forte sur ${pred.symbol} (${pred.trend_strength.toFixed(0)}%)`,
            severity: pred.trend === 'bearish' ? 'high' : 'low',
            icon: pred.trend === 'bullish' ? 'trending_up' : 'trending_down',
            source: 'prediction',
          })
        }
      }
    }

    // From market signals
    if (sentiment?.signals) {
      for (const sig of sentiment.signals) {
        items.push({
          type: sig.type,
          message: sig.message,
          severity: sig.type === 'sell' ? 'high' : sig.type === 'buy' ? 'low' : 'medium',
          icon: sig.type === 'buy' ? 'trending_up' : sig.type === 'sell' ? 'trending_down' : 'zap',
          source: 'signal',
        })
      }
    }

    const sevOrder = { high: 0, medium: 1, low: 2 }
    return items.sort((a, b) => sevOrder[a.severity] - sevOrder[b.severity])
  }, [predictions, sentiment])

  // Chart data for selected asset
  const selectedPrediction = predictions?.find(p => p.symbol === selectedAsset)
  const chartData = useMemo(() => {
    if (!selectedPrediction?.predictions) return []
    return selectedPrediction.predictions.map(p => ({
      date: p.date.slice(5),
      price: p.price,
      confidence_low: p.confidence_low,
      confidence_high: p.confidence_high,
    }))
  }, [selectedPrediction])

  // Smart price formatter for Y axis (handles tiny prices like PEPE)
  const formatPrice = (value: number) => {
    if (value === 0) return '0'
    const abs = Math.abs(value)
    if (abs >= 1) return formatCurrency(value).replace(/[€\s]/g, '')
    // For sub-cent values, use scientific-ish notation
    if (abs < 0.0001) {
      // Count leading zeros after decimal
      const str = abs.toFixed(10)
      const match = str.match(/^0\.0*/)
      const zeros = match ? match[0].length - 2 : 0
      const significant = (abs * Math.pow(10, zeros)).toFixed(2)
      return `${significant}e-${zeros}`
    }
    return abs.toFixed(6)
  }

  // Determine if support/resistance are within chart range (don't crush the scale)
  const showSupportResistance = useMemo(() => {
    if (!selectedPrediction || !chartData.length) return false
    const prices = chartData.map(d => d.price)
    const minP = Math.min(...prices, ...chartData.map(d => d.confidence_low))
    const maxP = Math.max(...prices, ...chartData.map(d => d.confidence_high))
    const range = maxP - minP || maxP * 0.1
    const s = selectedPrediction.support_level
    const r = selectedPrediction.resistance_level
    // Only show if support/resistance are within 3x the prediction range
    return s > 0 && r > 0 && s > minP - range * 2 && r < maxP + range * 2
  }, [selectedPrediction, chartData])

  // What-If
  const runWhatIf = async () => {
    if (!effectiveWhatIfSymbol) return
    setWhatIfLoading(true)
    try {
      const result = await predictionsApi.whatIf([{ symbol: effectiveWhatIfSymbol, change_percent: whatIfChange }])
      setWhatIfResult(result)
    } catch {
      // ignore
    }
    setWhatIfLoading(false)
  }

  const getTrendIcon = (trend: string) => {
    switch (trend?.toLowerCase()) {
      case 'bullish': return <TrendingUp className="h-4 w-4 text-green-500" />
      case 'bearish': return <TrendingDown className="h-4 w-4 text-red-500" />
      default: return <Minus className="h-4 w-4 text-yellow-500" />
    }
  }

  const getSignalBadge = (trend: string) => {
    if (trend === 'bullish')
      return { variant: 'default' as const, label: 'Haussier' }
    if (trend === 'bearish')
      return { variant: 'destructive' as const, label: 'Baissier' }
    return { variant: 'secondary' as const, label: 'Neutre' }
  }

  const getAlertIcon = (icon: string) => {
    switch (icon) {
      case 'shield': return <ShieldAlert className="h-5 w-5" />
      case 'trending_up': return <TrendingUp className="h-5 w-5" />
      case 'trending_down': return <TrendingDown className="h-5 w-5" />
      case 'zap': return <Zap className="h-5 w-5" />
      default: return <AlertTriangle className="h-5 w-5" />
    }
  }

  if (loadingPredictions || loadingSentiment) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  const totalAlerts = unifiedAlerts.length
  const highAlerts = unifiedAlerts.filter(a => a.severity === 'high').length

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Prédictions IA</h1>
          <p className="text-muted-foreground">Analyse prédictive et sentiment de marché</p>
        </div>
        <Select value={daysAhead.toString()} onValueChange={(v) => setDaysAhead(parseInt(v))}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 jours</SelectItem>
            <SelectItem value="14">14 jours</SelectItem>
            <SelectItem value="30">30 jours</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* ── Zone haute : Sentiment + Résumé Portfolio (1 rangée) ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Sentiment unifié */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-primary" />
                <span className="font-semibold">Sentiment marché</span>
              </div>
              {totalAlerts > 0 && (
                <Badge variant={highAlerts > 0 ? 'destructive' : 'secondary'} className="text-xs">
                  <Bell className="h-3 w-3 mr-1" />
                  {totalAlerts} signal{totalAlerts > 1 ? 'x' : ''}
                </Badge>
              )}
            </div>
            <div className="flex items-center justify-center">
              <FearGreedGauge value={sentiment?.fear_greed_index ?? 50} />
            </div>
            <div className="flex items-center justify-center gap-3 mt-3">
              <Badge variant={
                sentiment?.overall_sentiment === 'bullish' ? 'default' :
                sentiment?.overall_sentiment === 'bearish' ? 'destructive' : 'secondary'
              }>
                {sentiment?.overall_sentiment?.replace('_', ' ') ?? 'N/A'}
              </Badge>
              <span className="text-sm text-muted-foreground capitalize">
                {sentiment?.market_phase?.replace('_', ' ') ?? ''}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Résumé portfolio */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-5 w-5 text-primary" />
              <span className="font-semibold">Prévision portefeuille</span>
              <span className="text-xs text-muted-foreground ml-auto">{summary?.days_ahead ?? daysAhead}j</span>
            </div>

            {summary ? (
              <div className="space-y-4">
                {/* Main metric: expected change */}
                <div className="text-center">
                  <div className={`text-4xl font-bold flex items-center justify-center gap-2 ${
                    summary.expected_change_percent >= 0 ? 'text-green-500' : 'text-red-500'
                  }`}>
                    {summary.expected_change_percent >= 0 ? (
                      <ArrowUp className="h-7 w-7" />
                    ) : (
                      <ArrowDown className="h-7 w-7" />
                    )}
                    {Math.abs(summary.expected_change_percent).toFixed(2)}%
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {formatCurrency(summary.total_current_value)} → {formatCurrency(summary.total_predicted_value)}
                  </p>
                </div>

                {/* Trend distribution bar */}
                <div className="space-y-2">
                  <div className="flex h-3 rounded-full overflow-hidden bg-muted">
                    {summary.bullish_assets > 0 && (
                      <div
                        className="bg-green-500 transition-all"
                        style={{ width: `${(summary.bullish_assets / (summary.bullish_assets + summary.neutral_assets + summary.bearish_assets)) * 100}%` }}
                      />
                    )}
                    {summary.neutral_assets > 0 && (
                      <div
                        className="bg-yellow-500 transition-all"
                        style={{ width: `${(summary.neutral_assets / (summary.bullish_assets + summary.neutral_assets + summary.bearish_assets)) * 100}%` }}
                      />
                    )}
                    {summary.bearish_assets > 0 && (
                      <div
                        className="bg-red-500 transition-all"
                        style={{ width: `${(summary.bearish_assets / (summary.bullish_assets + summary.neutral_assets + summary.bearish_assets)) * 100}%` }}
                      />
                    )}
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      {summary.bullish_assets} haussier
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-yellow-500" />
                      {summary.neutral_assets} neutre
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-red-500" />
                      {summary.bearish_assets} baissier
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">Aucune donnée</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Zone basse : Tabs ── */}
      <Tabs defaultValue="predictions" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="predictions" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Prédictions
          </TabsTrigger>
          <TabsTrigger value="signals" className="flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Signaux
            {highAlerts > 0 && (
              <span className="ml-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
                {highAlerts}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="simulation" className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            Simulation
          </TabsTrigger>
        </TabsList>

        {/* ── Tab: Prédictions ── */}
        <TabsContent value="predictions">
          <Card>
            <CardHeader>
              <CardTitle>Prédictions par actif</CardTitle>
              <CardDescription>Cliquez sur un actif pour voir la projection visuelle</CardDescription>
            </CardHeader>
            <CardContent>
              {predictions && predictions.length > 0 ? (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-3 px-4 font-medium">Actif</th>
                          <th className="text-left py-3 px-4 font-medium">Variation</th>
                          <th className="text-center py-3 px-4 font-medium">Signal</th>
                          <th className="text-center py-3 px-4 font-medium">Score</th>
                          <th className="w-8"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {predictions.map((pred) => {
                          const signal = getSignalBadge(pred.trend)
                          const isSelected = selectedAsset === pred.symbol
                          return (
                            <tr
                              key={pred.symbol}
                              className={`border-b cursor-pointer transition-colors ${isSelected ? 'bg-primary/5' : 'hover:bg-muted/50'}`}
                              onClick={() => setSelectedAsset(isSelected ? null : pred.symbol)}
                            >
                              <td className="py-3 px-4">
                                <p className="font-medium">{pred.symbol}</p>
                                <p className="text-xs text-muted-foreground">{pred.name}</p>
                              </td>
                              <td className="py-3 px-4">
                                <VariationBar percent={pred.change_percent} />
                              </td>
                              <td className="text-center py-3 px-4">
                                <div className="flex items-center justify-center gap-2">
                                  {getTrendIcon(pred.trend)}
                                  <Badge variant={signal.variant} className="text-xs">{signal.label}</Badge>
                                </div>
                              </td>
                              <td className="py-3 px-4">
                                <div className="flex justify-center">
                                  <CombinedScore accuracy={pred.accuracy} consensus={pred.consensus_score} />
                                </div>
                              </td>
                              <td className="py-3 px-4">
                                {isSelected ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Confidence cone chart */}
                  {selectedPrediction && chartData.length > 0 && (
                    <div className="mt-6 pt-6 border-t">
                      <h4 className="font-medium mb-1">
                        Projection {selectedPrediction.symbol} — {daysAhead} jours
                      </h4>
                      <p className="text-sm text-muted-foreground mb-2">
                        Support: {formatCurrency(selectedPrediction.support_level)} · Résistance: {formatCurrency(selectedPrediction.resistance_level)}
                      </p>
                      {selectedPrediction.models_detail && selectedPrediction.models_detail.length > 0 ? (
                        <div className="flex flex-wrap gap-2 mb-4">
                          {selectedPrediction.models_detail
                            .sort((a, b) => b.weight_pct - a.weight_pct)
                            .map((m) => (
                              <Badge key={m.name} variant="outline" className="text-xs gap-1">
                                {m.name} {m.weight_pct}%
                                {m.mape != null && (
                                  <span className="text-muted-foreground ml-0.5">(MAPE {m.mape.toFixed(1)}%)</span>
                                )}
                                {m.trend === 'bullish' ? (
                                  <ArrowUp className="h-3 w-3 text-emerald-500" />
                                ) : m.trend === 'bearish' ? (
                                  <ArrowDown className="h-3 w-3 text-red-500" />
                                ) : (
                                  <Minus className="h-3 w-3 text-gray-400" />
                                )}
                              </Badge>
                            ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground mb-4">Modèle: {selectedPrediction.model_used}</p>
                      )}
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData}>
                            <defs>
                              <linearGradient id="confGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                            <YAxis
                              domain={[(dataMin: number) => dataMin * 0.995, (dataMax: number) => dataMax * 1.005]}
                              tickFormatter={formatPrice}
                              tick={{ fontSize: 11 }}
                              width={90}
                              allowDecimals
                            />
                            <RechartsTooltip
                              formatter={(value: number, name: string) => {
                                const labels: Record<string, string> = {
                                  confidence_high: 'Borne haute',
                                  confidence_low: 'Borne basse',
                                  price: 'Prix prédit',
                                }
                                return [formatCurrency(value), labels[name] || name]
                              }}
                            />
                            <Area type="monotone" dataKey="confidence_high" stroke="none" fill="url(#confGradient)" fillOpacity={1} />
                            <Area type="monotone" dataKey="confidence_low" stroke="none" fill="#ffffff" fillOpacity={0.8} />
                            <Area type="monotone" dataKey="price" stroke="#3b82f6" strokeWidth={2} strokeDasharray="6 3" fill="none" />
                            {showSupportResistance && (
                              <>
                                <ReferenceLine y={selectedPrediction.support_level} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Support', position: 'left', fontSize: 10, fill: '#ef4444' }} />
                                <ReferenceLine y={selectedPrediction.resistance_level} stroke="#10b981" strokeDasharray="4 4" label={{ value: 'Résistance', position: 'left', fontSize: 10, fill: '#10b981' }} />
                              </>
                            )}
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>

                      {/* SHAP Explanations */}
                      {selectedPrediction.explanations && selectedPrediction.explanations.length > 0 && (
                        <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
                          <div className="flex items-center gap-2 mb-3">
                            <Brain className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">Facteurs clés de la prédiction</span>
                          </div>
                          <div className="space-y-2">
                            {selectedPrediction.explanations.map((exp, i) => {
                              const isUp = exp.direction === 'hausse'
                              const maxImportance = Math.max(...selectedPrediction.explanations!.map(e => e.importance))
                              const barWidth = maxImportance > 0 ? (exp.importance / maxImportance) * 100 : 0
                              return (
                                <div key={i} className="flex items-center gap-3">
                                  <span className="text-xs text-muted-foreground w-28 shrink-0 truncate" title={exp.feature_name}>
                                    {exp.feature_name}
                                  </span>
                                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                                    <div
                                      className={`h-full rounded-full ${isUp ? 'bg-green-500' : 'bg-red-500'}`}
                                      style={{ width: `${barWidth}%` }}
                                    />
                                  </div>
                                  <div className="flex items-center gap-1 w-16 justify-end">
                                    {isUp ? (
                                      <ArrowUp className="h-3 w-3 text-green-500" />
                                    ) : (
                                      <ArrowDown className="h-3 w-3 text-red-500" />
                                    )}
                                    <span className={`text-xs font-medium ${isUp ? 'text-green-500' : 'text-red-500'}`}>
                                      {exp.direction}
                                    </span>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                          <p className="text-xs text-muted-foreground mt-2">
                            Basé sur l'analyse SHAP du modèle XGBoost
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-center text-muted-foreground py-8">Aucune prédiction disponible</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab: Signaux & Alertes (fusionnés) ── */}
        <TabsContent value="signals">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-orange-500" />
                Signaux & alertes
              </CardTitle>
              <CardDescription>Alertes prédictives et signaux de marché combinés</CardDescription>
            </CardHeader>
            <CardContent>
              {unifiedAlerts.length > 0 ? (
                <div className="space-y-3">
                  {unifiedAlerts.map((alert, i) => (
                    <div
                      key={i}
                      className={`p-4 rounded-lg border flex items-start gap-3 ${
                        alert.severity === 'high' ? 'bg-red-500/10 border-red-500/20' :
                        alert.severity === 'medium' ? 'bg-yellow-500/10 border-yellow-500/20' :
                        'bg-green-500/10 border-green-500/20'
                      }`}
                    >
                      <div className={
                        alert.severity === 'high' ? 'text-red-500' :
                        alert.severity === 'medium' ? 'text-yellow-500' : 'text-green-500'
                      }>
                        {getAlertIcon(alert.icon)}
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-sm">{alert.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          {alert.symbol && <Badge variant="outline" className="text-xs">{alert.symbol}</Badge>}
                          <span className="text-xs text-muted-foreground capitalize">{alert.type.replace('_', ' ')}</span>
                          <span className="text-xs text-muted-foreground">·</span>
                          <span className="text-xs text-muted-foreground">{alert.source === 'signal' ? 'Signal marché' : 'Prédiction'}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-center text-muted-foreground py-8">Aucun signal détecté</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab: Simulation ── */}
        <TabsContent value="simulation" className="space-y-4">
          {/* What-If */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-blue-500" />
                Scénario What-If
              </CardTitle>
              <CardDescription>Simulez l'impact d'une variation de prix sur votre portefeuille</CardDescription>
            </CardHeader>
            <CardContent>
              {predictions && predictions.length > 0 ? (
                <div className="grid gap-6 lg:grid-cols-2">
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium mb-2 block">Actif</label>
                      <Select value={effectiveWhatIfSymbol} onValueChange={setWhatIfSymbol}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {predictions.map(p => (
                            <SelectItem key={p.symbol} value={p.symbol}>{p.symbol} - {p.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <label className="text-sm font-medium mb-2 block">
                        Variation: <span className={`font-bold ${whatIfChange >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {whatIfChange >= 0 ? '+' : ''}{whatIfChange}%
                        </span>
                      </label>
                      <input
                        type="range"
                        min="-50"
                        max="100"
                        value={whatIfChange}
                        onChange={(e) => { setWhatIfChange(parseInt(e.target.value)); setWhatIfResult(null) }}
                        onMouseUp={runWhatIf}
                        onTouchEnd={runWhatIf}
                        className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-primary"
                      />
                      <div className="flex justify-between text-xs text-muted-foreground mt-1">
                        <span>-50%</span>
                        <span>0%</span>
                        <span>+100%</span>
                      </div>
                    </div>

                    {whatIfLoading && <Loader2 className="h-5 w-5 animate-spin text-primary" />}

                    {whatIfResult && (
                      <div className="space-y-3 pt-2">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 rounded-lg bg-muted/50">
                            <p className="text-xs text-muted-foreground">Valeur actuelle</p>
                            <p className="text-lg font-bold">{formatCurrency(whatIfResult.current_value)}</p>
                          </div>
                          <div className={`p-3 rounded-lg ${whatIfResult.impact_percent >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                            <p className="text-xs text-muted-foreground">Valeur simulée</p>
                            <p className={`text-lg font-bold ${whatIfResult.impact_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              {formatCurrency(whatIfResult.simulated_value)}
                            </p>
                          </div>
                        </div>
                        <p className={`text-center font-bold text-lg ${whatIfResult.impact_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {whatIfResult.impact_percent >= 0 ? '+' : ''}{whatIfResult.impact_percent.toFixed(2)}% sur le portefeuille
                        </p>
                      </div>
                    )}
                  </div>

                  {whatIfResult && whatIfResult.per_asset.length > 0 && (
                    <div>
                      <p className="text-sm font-medium mb-2">Impact par actif</p>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={whatIfResult.per_asset.map(a => ({ name: a.symbol, impact: a.impact }))}
                            layout="vertical"
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis type="number" tickFormatter={(v) => formatCurrency(v).replace('€', '')} />
                            <YAxis type="category" dataKey="name" width={50} tick={{ fontSize: 12 }} />
                            <RechartsTooltip formatter={(value: number) => formatCurrency(value)} />
                            <Bar dataKey="impact" radius={4}>
                              {whatIfResult.per_asset.map((a, i) => (
                                <Cell key={i} fill={a.impact >= 0 ? '#10b981' : '#ef4444'} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-center text-muted-foreground py-8">Aucun actif disponible</p>
              )}
            </CardContent>
          </Card>

          {/* Anomalies */}
          {anomalies && anomalies.filter(a => a.is_anomaly).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                  Anomalies détectées
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {anomalies.filter(a => a.is_anomaly).map((anomaly, index) => (
                    <div
                      key={index}
                      className={`p-4 rounded-lg border ${
                        anomaly.severity === 'high' ? 'bg-red-500/10 border-red-500/20' :
                        anomaly.severity === 'medium' ? 'bg-yellow-500/10 border-yellow-500/20' :
                        'bg-blue-500/10 border-blue-500/20'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold">{anomaly.symbol}</span>
                          <Badge variant={anomaly.severity === 'high' ? 'destructive' : 'secondary'}>
                            {anomaly.anomaly_type}
                          </Badge>
                        </div>
                        <span className={`font-medium ${anomaly.price_change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {anomaly.price_change_percent >= 0 ? '+' : ''}{anomaly.price_change_percent.toFixed(2)}%
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* ── Disclaimer discret ── */}
      <p className="flex items-center gap-2 text-xs text-muted-foreground px-1">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        Les prédictions sont basées sur des modèles statistiques et ne constituent pas des conseils financiers.
      </p>
    </div>
  )
}
