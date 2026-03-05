import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
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
import { queryKeys } from '@/lib/queryKeys'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Brain,
  Loader2,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  Minus,
  Zap,
  ShieldAlert,
  Target,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  BarChart3,
  Bell,
  Activity,
  Droplets,
  Layers,
  Repeat,
  Eye,
  EyeOff,
  History,
  CheckCircle,
  XCircle,
  Clock,
  Flame,
} from 'lucide-react'
import { type DisplayThresholds, DEFAULT_DISPLAY_THRESHOLDS } from '@/types'
import { Button } from '@/components/ui/button'
import {
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
  Line,
  ComposedChart,
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
  skill_score: number
  hit_rate: number
  hit_rate_significant: boolean
  hit_rate_n_samples: number
  reliability_score: number
  model_confidence: string
  models_agree: boolean
  models_detail?: { name: string; weight_pct: number; trend: string; mape?: number }[]
  explanations?: { feature_name: string; importance: number; direction: string }[]
  regime_info?: {
    dominant_regime: string
    confidence: number
    probabilities: Record<string, number>
    timeframe_alignment?: string
    weekly_regime?: string | null
    note?: string
    liquidity_warning?: string
    regime_price_adjustment?: boolean
    adjustment_factor?: number
  }
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

interface MarketCycleData {
  market_regime: {
    dominant_regime: string
    confidence: number
    probabilities: Record<string, number>
    description: string
  } | null
  market_signals: Array<{
    name: string
    value: number
    signal: string
    strength: number
    description: string
  }>
  portfolio_regime: {
    dominant_regime: string
    probabilities: Record<string, number>
  }
  per_asset: Array<{
    symbol: string
    name: string
    asset_type: string
    value: number
    dominant_regime: string
    confidence: number
    probabilities: Record<string, number>
  }>
  cycle_position: number
  cycle_advice: Array<{
    title: string
    description: string
    action: string
    priority: string
  }>
  fear_greed: number | null
  btc_dominance: number | null
  display_thresholds?: DisplayThresholds
  top_bottom_estimates?: {
    btc: TopBottomEstimate | null
    per_asset: TopBottomEstimate[]
  }
  distribution_diagnostic?: Array<{
    symbol: string
    name: string
    dominant_regime: string
    top_bearish_prob: number
    rsi: number | null
    weight_pct: number
    signals: string[]
    sell_priority: string
  }>
  time_to_pivot?: {
    current_phase: string
    next_phase: string
    estimated_days: number
    confidence: number
    cycle_position: number
  }
}

interface TopBottomEstimate {
  symbol: string
  current_price: number
  next_bottom: {
    estimated_price: number
    estimated_days: number
    estimated_date: string
    confidence: number
    distance_pct: number
    method: string
    support_level: number
  }
  next_top: {
    estimated_price: number
    estimated_days: number
    estimated_date: string
    confidence: number
    distance_pct: number
    method: string
    resistance_level: number
  }
  current_regime: string
  cycle_position: number
  ou_parameters: {
    mu: number
    theta: number
    sigma: number
  }
}

// ── Fear & Greed Arc Gauge (large) ──────────────────────────────────
const FearGreedGauge = ({ value, thresholds }: { value: number; thresholds?: DisplayThresholds['fear_greed'] }) => {
  const clampedValue = Math.max(0, Math.min(100, value))
  const angle = Math.max(1, (clampedValue / 100) * 180) // min 1° to avoid zero-length arc
  const radians = (angle * Math.PI) / 180
  const x = 60 - 45 * Math.cos(radians)
  const y = 55 - 45 * Math.sin(radians)

  const fg = thresholds ?? DEFAULT_DISPLAY_THRESHOLDS.fear_greed

  // Gradient colors
  const getColor = (v: number) => {
    if (v >= fg.extreme_greed) return '#22c55e'
    if (v >= fg.greed) return '#84cc16'
    if (v >= fg.fear) return '#eab308'
    if (v >= fg.extreme_fear) return '#f97316'
    return '#ef4444'
  }
  const getLabel = (v: number) => {
    if (v >= fg.extreme_greed) return 'Extrême avidité'
    if (v >= fg.greed) return 'Avidité'
    if (v >= fg.fear) return 'Neutre'
    if (v >= fg.extreme_fear) return 'Peur'
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

// ── Cycle Position Gauge ──────────────────────────────────────────────
const CycleGauge = ({ position }: { position: number }) => {
  // 0=creux, 15=accumulation, 40=expansion, 65=distribution, 85=baissier
  const clampedPos = Math.max(0, Math.min(100, position))
  const angle = (clampedPos / 100) * 360
  const radians = ((angle - 90) * Math.PI) / 180
  const cx = 60, cy = 60, r = 45
  const nx = cx + r * Math.cos(radians)
  const ny = cy + r * Math.sin(radians)

  // Map cycle_position to phase label and color
  const getPhase = (pos: number): { label: string; color: string } => {
    if (pos < 15) return { label: 'Creux', color: '#3b82f6' }
    if (pos < 40) return { label: 'Accumulation', color: '#06b6d4' }
    if (pos < 65) return { label: 'Expansion', color: '#22c55e' }
    if (pos < 85) return { label: 'Distribution', color: '#f59e0b' }
    return { label: 'Euphorie', color: '#ef4444' }
  }
  const phase = getPhase(clampedPos)

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="140" viewBox="0 0 120 120">
        {/* Background ring */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/20" />
        {/* Colored segments (subtle) */}
        {[
          { start: -90, end: -36, c: '#3b82f6' },   // 0-15: Creux (blue)
          { start: -36, end: 54, c: '#06b6d4' },     // 15-40: Accumulation (cyan)
          { start: 54, end: 144, c: '#22c55e' },     // 40-65: Expansion (green)
          { start: 144, end: 216, c: '#f59e0b' },    // 65-85: Distribution (amber)
          { start: 216, end: 270, c: '#ef4444' },     // 85-100: Euphorie (red)
        ].map(({ start, end, c }, i) => {
          const s = (start * Math.PI) / 180
          const e = (end * Math.PI) / 180
          const x1 = cx + r * Math.cos(s)
          const y1 = cy + r * Math.sin(s)
          const x2 = cx + r * Math.cos(e)
          const y2 = cy + r * Math.sin(e)
          const largeArc = (end - start) > 180 ? 1 : 0
          return (
            <path
              key={i}
              d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
              fill="none"
              stroke={c}
              strokeWidth="8"
              opacity={0.2}
            />
          )
        })}
        {/* Needle dot */}
        <circle cx={nx} cy={ny} r="6" fill={phase.color} stroke="white" strokeWidth="2" />
        {/* Center text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill={phase.color} fontSize="14" fontWeight="bold">
          {phase.label}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill="currentColor" fontSize="10" className="fill-muted-foreground">
          Position: {clampedPos}
        </text>
        {/* Labels */}
        <text x={cx} y="10" textAnchor="middle" fontSize="7" className="fill-muted-foreground">Creux</text>
        <text x="112" y={cy + 3} textAnchor="start" fontSize="7" className="fill-muted-foreground">Expansion</text>
        <text x={cx} y="116" textAnchor="middle" fontSize="7" className="fill-muted-foreground">Distribution</text>
        <text x="2" y={cy + 3} textAnchor="start" fontSize="7" className="fill-muted-foreground">Euphorie</text>
      </svg>
    </div>
  )
}

// ── Reliability Score (skill_score + hit_rate, statistically validated) ──
const ReliabilityScore = ({ reliabilityScore, skillScore, hitRate, hitRateSignificant, hitRateN, modelConfidence }: {
  reliabilityScore: number
  skillScore: number
  hitRate: number
  hitRateSignificant: boolean
  hitRateN: number
  modelConfidence: string
}) => {
  const score = Math.round(reliabilityScore)
  const color = score >= 60 ? 'bg-green-500' : score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = score >= 60 ? 'text-green-500' : score >= 40 ? 'text-yellow-500' : 'text-red-500'
  const label = modelConfidence === 'useful' ? 'Utile' : modelConfidence === 'uncertain' ? 'Incertain' : 'Non fiable'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 cursor-help">
            <div className="w-14 h-2 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
            </div>
            <span className={`text-xs font-bold ${textColor}`}>{score}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs font-medium mb-1">{label}</p>
          <p className="text-xs">Skill: {skillScore.toFixed(0)}% · Direction: {hitRate.toFixed(0)}% ({hitRateN} tests{hitRateSignificant ? ', significatif' : ', non significatif'})</p>
          <p className="text-xs text-muted-foreground mt-1">Mesure si le modèle fait mieux qu'une prédiction naïve (prix inchangé)</p>
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

// ── Top / Bottom Estimates Card ─────────────────────────────────────
const TopBottomCard = ({ estimates }: { estimates: MarketCycleData['top_bottom_estimates'] }) => {
  if (!estimates) return null
  const { btc, per_asset } = estimates
  const allEstimates = btc ? [btc, ...per_asset.filter(a => a.symbol !== 'BTC')] : per_asset

  if (allEstimates.length === 0) return null

  const regimeLabels: Record<string, string> = {
    bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux', neutral: 'Neutre',
  }

  const formatDate = (d: string) => {
    const [, m, day] = d.split('-')
    const months = ['', 'jan', 'fév', 'mar', 'avr', 'mai', 'juin', 'juil', 'août', 'sep', 'oct', 'nov', 'déc']
    return `${parseInt(day)} ${months[parseInt(m)]}`
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          <Target className="h-4 w-4 text-primary" />
          Estimations Top / Bottom
        </CardTitle>
        <CardDescription>
          Prix cibles et dates estimés via mean-reversion (Ornstein-Uhlenbeck) + niveaux support/résistance
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                <th className="text-center py-2 px-3 text-xs font-medium">Prix actuel</th>
                <th className="text-center py-2 px-3 text-xs font-medium">
                  <span className="flex items-center justify-center gap-1">
                    <ArrowDown className="h-3 w-3 text-blue-500" />
                    Bottom estimé
                  </span>
                </th>
                <th className="text-center py-2 px-3 text-xs font-medium">
                  <span className="flex items-center justify-center gap-1">
                    <ArrowUp className="h-3 w-3 text-amber-500" />
                    Top estimé
                  </span>
                </th>
                <th className="text-center py-2 px-3 text-xs font-medium">Confiance</th>
              </tr>
            </thead>
            <tbody>
              {allEstimates.map((est) => {
                const isBtc = est.symbol === 'BTC'
                return (
                  <tr key={est.symbol} className={`border-b last:border-0 ${isBtc ? 'bg-primary/5' : ''}`}>
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{est.symbol}</span>
                        {isBtc && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0">Réf.</Badge>
                        )}
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                          est.current_regime === 'bearish' ? 'text-red-500 border-red-500/30' :
                          est.current_regime === 'bullish' ? 'text-green-500 border-green-500/30' :
                          est.current_regime === 'top' ? 'text-amber-500 border-amber-500/30' :
                          est.current_regime === 'bottom' ? 'text-blue-500 border-blue-500/30' :
                          'text-gray-500'
                        }`}>
                          {regimeLabels[est.current_regime] || est.current_regime}
                        </Badge>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className="text-sm font-medium tabular-nums">{formatCurrency(est.current_price)}</span>
                    </td>
                    {/* Bottom */}
                    <td className="py-3 px-3">
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="text-sm font-bold text-blue-500 tabular-nums">
                          {formatCurrency(est.next_bottom.estimated_price)}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground">
                            {formatDate(est.next_bottom.estimated_date)} (~{est.next_bottom.estimated_days}j)
                          </span>
                          <span className="text-[10px] font-medium text-blue-500">
                            -{est.next_bottom.distance_pct.toFixed(1)}%
                          </span>
                        </div>
                        {/* Visual distance bar */}
                        <div className="w-20 h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                          <div
                            className="h-full rounded-full bg-blue-500"
                            style={{ width: `${Math.min(100, est.next_bottom.distance_pct * 3)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    {/* Top */}
                    <td className="py-3 px-3">
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="text-sm font-bold text-amber-500 tabular-nums">
                          {formatCurrency(est.next_top.estimated_price)}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground">
                            {formatDate(est.next_top.estimated_date)} (~{est.next_top.estimated_days}j)
                          </span>
                          <span className="text-[10px] font-medium text-amber-500">
                            +{est.next_top.distance_pct.toFixed(1)}%
                          </span>
                        </div>
                        <div className="w-20 h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                          <div
                            className="h-full rounded-full bg-amber-500"
                            style={{ width: `${Math.min(100, est.next_top.distance_pct * 3)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    {/* Confidence */}
                    <td className="py-3 px-3 text-center">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="flex flex-col items-center gap-1 cursor-help">
                              <div className="w-10 h-1.5 rounded-full bg-muted overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    est.next_bottom.confidence >= 0.6 ? 'bg-green-500' :
                                    est.next_bottom.confidence >= 0.3 ? 'bg-yellow-500' : 'bg-red-500'
                                  }`}
                                  style={{ width: `${(est.next_bottom.confidence * 100).toFixed(0)}%` }}
                                />
                              </div>
                              <span className={`text-[10px] font-medium ${
                                est.next_bottom.confidence >= 0.6 ? 'text-green-500' :
                                est.next_bottom.confidence >= 0.3 ? 'text-yellow-500' : 'text-red-500'
                              }`}>
                                {(est.next_bottom.confidence * 100).toFixed(0)}%
                              </span>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            <p className="text-xs">
                              Confiance basée sur : clarté du régime, significativité du theta OU ({est.ou_parameters.theta.toFixed(3)}), et quantité de données historiques
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Disclaimer */}
        <div className="mt-4 flex items-start gap-2 p-2 rounded bg-muted/30">
          <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            Ces estimations sont basées sur un modèle de mean-reversion (Ornstein-Uhlenbeck) et des niveaux support/résistance historiques.
            Elles représentent des cibles statistiques, pas des prédictions certaines. En conditions extrêmes (crash, euphorie),
            les prix réels peuvent largement dépasser ces bornes.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Track Record Panel (lazy-loaded per asset) ──────────────────────
const TrackRecordPanel = ({ symbol }: { symbol: string }) => {
  const { data, isLoading } = useQuery<{
    symbol: string
    records: Array<{
      date: string | null
      target_date: string | null
      predicted_price: number | null
      actual_price: number | null
      mape: number | null
      direction_correct: boolean | null
      ci_covered: boolean | null
    }>
    summary: {
      total_checked: number
      avg_mape: number | null
      direction_accuracy: number | null
      ci_coverage: number | null
    }
  }>({
    queryKey: queryKeys.predictions.trackRecord(symbol),
    queryFn: () => predictionsApi.getTrackRecord(symbol),
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="text-xs text-muted-foreground">Chargement du track record...</span>
      </div>
    )
  }

  if (!data || data.summary.total_checked === 0) {
    return (
      <div className="py-3">
        <p className="text-xs text-muted-foreground">Aucun historique de prédiction vérifié pour {symbol}</p>
      </div>
    )
  }

  const s = data.summary
  const mapeColor = s.avg_mape != null ? (s.avg_mape <= 5 ? 'text-green-500' : s.avg_mape <= 10 ? 'text-yellow-500' : 'text-red-500') : 'text-muted-foreground'
  const dirColor = s.direction_accuracy != null ? (s.direction_accuracy >= 60 ? 'text-green-500' : s.direction_accuracy >= 50 ? 'text-yellow-500' : 'text-red-500') : 'text-muted-foreground'
  const ciColor = s.ci_coverage != null ? (s.ci_coverage >= 90 ? 'text-green-500' : s.ci_coverage >= 70 ? 'text-yellow-500' : 'text-red-500') : 'text-muted-foreground'

  return (
    <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
      <div className="flex items-center gap-2 mb-3">
        <History className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Track Record</span>
        <Badge variant="outline" className="text-[10px] ml-auto">{s.total_checked} prédictions vérifiées</Badge>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Erreur moy.</p>
          <p className={`text-sm font-bold ${mapeColor}`}>
            {s.avg_mape != null ? `${s.avg_mape.toFixed(1)}%` : 'N/A'}
          </p>
          <p className="text-[10px] text-muted-foreground">MAPE</p>
        </div>
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Direction</p>
          <p className={`text-sm font-bold ${dirColor}`}>
            {s.direction_accuracy != null ? `${s.direction_accuracy.toFixed(0)}%` : 'N/A'}
          </p>
          <p className="text-[10px] text-muted-foreground">précision</p>
        </div>
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Couverture IC</p>
          <p className={`text-sm font-bold ${ciColor}`}>
            {s.ci_coverage != null ? `${s.ci_coverage.toFixed(0)}%` : 'N/A'}
          </p>
          <p className="text-[10px] text-muted-foreground">dans les bandes</p>
        </div>
      </div>

      {/* Recent records mini-table */}
      {data.records.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-1.5 px-2 text-[10px] font-medium text-muted-foreground">Date</th>
                <th className="text-right py-1.5 px-2 text-[10px] font-medium text-muted-foreground">Prédit</th>
                <th className="text-right py-1.5 px-2 text-[10px] font-medium text-muted-foreground">Réel</th>
                <th className="text-right py-1.5 px-2 text-[10px] font-medium text-muted-foreground">Erreur</th>
                <th className="text-center py-1.5 px-2 text-[10px] font-medium text-muted-foreground">Dir.</th>
              </tr>
            </thead>
            <tbody>
              {data.records.slice(0, 8).map((r, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-1.5 px-2 text-[10px] text-muted-foreground">
                    {r.target_date ? new Date(r.target_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }) : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-[10px] text-right tabular-nums">
                    {r.predicted_price != null ? formatCurrency(r.predicted_price) : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-[10px] text-right tabular-nums">
                    {r.actual_price != null ? formatCurrency(r.actual_price) : '—'}
                  </td>
                  <td className={`py-1.5 px-2 text-[10px] text-right tabular-nums ${
                    r.mape != null ? (r.mape <= 5 ? 'text-green-500' : r.mape <= 10 ? 'text-yellow-500' : 'text-red-500') : ''
                  }`}>
                    {r.mape != null ? `${r.mape.toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {r.direction_correct != null ? (
                      r.direction_correct ? (
                        <CheckCircle className="h-3 w-3 text-green-500 mx-auto" />
                      ) : (
                        <XCircle className="h-3 w-3 text-red-500 mx-auto" />
                      )
                    ) : <span className="text-[10px] text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
  const [showReality, setShowReality] = useState(false)
  const { toast } = useToast()

  const { data: portfolioPredictions, isLoading: loadingPredictions } = useQuery({
    queryKey: queryKeys.predictions.portfolio(daysAhead),
    queryFn: () => predictionsApi.getPortfolioPredictions(daysAhead),
    placeholderData: keepPreviousData,
  })

  const { data: anomalies, isError: anomaliesError } = useQuery<Anomaly[]>({
    queryKey: queryKeys.predictions.anomalies,
    queryFn: predictionsApi.getAnomalies,
  })

  const { data: sentiment, isLoading: loadingSentiment, isError: sentimentError } = useQuery<MarketSentiment>({
    queryKey: queryKeys.predictions.marketSentiment,
    queryFn: predictionsApi.getMarketSentiment,
  })

  const { data: marketCycle, isLoading: loadingCycle } = useQuery<MarketCycleData>({
    queryKey: queryKeys.predictions.marketCycle,
    queryFn: predictionsApi.getMarketCycle,
  })

  const { data: backtestData, isLoading: loadingBacktest } = useQuery<{
    per_asset: Array<{
      symbol: string
      mape: number | null
      direction_accuracy: number | null
      points: Array<{ date: string; predicted: number; actual: number }>
    }>
    overall_mape: number | null
    overall_direction_accuracy: number | null
    needs_retraining: boolean
  }>({
    queryKey: queryKeys.predictions.backtest(daysAhead),
    queryFn: () => predictionsApi.getBacktest(daysAhead),
    enabled: showReality,
  })

  const summary = portfolioPredictions?.summary as PortfolioPredictionSummary | undefined
  const predictions = portfolioPredictions?.predictions as PortfolioPrediction[] | undefined
  const dt: DisplayThresholds = (portfolioPredictions as Record<string, unknown>)?.display_thresholds as DisplayThresholds ?? DEFAULT_DISPLAY_THRESHOLDS

  // Reset What-If state when horizon changes
  useEffect(() => {
    setWhatIfResult(null)
    setWhatIfChange(0)
    setWhatIfSymbol('')
  }, [daysAhead])

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
        if (pred.trend_strength > dt.trend_strength.strong) {
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
  }, [predictions, sentiment, dt])

  // Chart data for selected asset
  const selectedPrediction = predictions?.find(p => p.symbol === selectedAsset)

  // Format date to match Dashboard (fr-FR short)
  const formatDateLabel = (dateStr: string) => {
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
    } catch {
      return dateStr.slice(5)
    }
  }

  interface ChartPoint {
    date: string
    price?: number
    confidence_low?: number
    confidence_high?: number
    actual?: number
    predicted_past?: number
    isToday: boolean
  }

  const chartData = useMemo((): ChartPoint[] => {
    if (!selectedPrediction?.predictions) return []

    // Backtest actual data for this asset
    const assetBacktest = showReality && backtestData
      ? backtestData.per_asset?.find(a => a.symbol === selectedPrediction.symbol)
      : null

    // Build historical "reality" points (before today)
    const realityPoints: ChartPoint[] = assetBacktest?.points?.map(p => ({
      date: formatDateLabel(p.date),
      actual: p.actual,
      predicted_past: p.predicted,
      isToday: false,
    })) ?? []

    // Add current price as day 0 anchor point
    const currentPoint: ChartPoint = {
      date: "Auj.",
      price: selectedPrediction.current_price,
      confidence_low: selectedPrediction.current_price,
      confidence_high: selectedPrediction.current_price,
      actual: showReality ? selectedPrediction.current_price : undefined,
      isToday: true,
    }

    // Future prediction points
    const futurePoints: ChartPoint[] = selectedPrediction.predictions.map(p => ({
      date: formatDateLabel(p.date),
      price: p.price,
      confidence_low: p.confidence_low,
      confidence_high: p.confidence_high,
      isToday: false,
    }))

    if (showReality && realityPoints.length > 0) {
      return [...realityPoints, currentPoint, ...futurePoints]
    }

    return [currentPoint, ...futurePoints]
  }, [selectedPrediction, showReality, backtestData])

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
    const allPrices = chartData.flatMap(d => [d.price, d.confidence_low, d.confidence_high, d.actual].filter((v): v is number => v != null))
    if (allPrices.length === 0) return false
    const minP = Math.min(...allPrices)
    const maxP = Math.max(...allPrices)
    const range = maxP - minP || maxP * 0.1
    const s = selectedPrediction.support_level
    const r = selectedPrediction.resistance_level
    // Only show if support/resistance are within 3x the prediction range
    return s > 0 && r > 0 && s > minP - range * 2 && r < maxP + range * 2
  }, [selectedPrediction, chartData])

  // What-If (use ref to read latest change value, avoiding race condition)
  const whatIfChangeRef = useRef(whatIfChange)
  whatIfChangeRef.current = whatIfChange

  const runWhatIf = async () => {
    if (!effectiveWhatIfSymbol) return
    setWhatIfResult(null)
    setWhatIfLoading(true)
    try {
      const result = await predictionsApi.whatIf([{ symbol: effectiveWhatIfSymbol, change_percent: whatIfChangeRef.current }])
      setWhatIfResult(result)
    } catch (err) {
      toast({ title: 'Erreur', description: 'Impossible de lancer la simulation What-If', variant: 'destructive' })
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
      {/* ── Disclaimer banner ── */}
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-yellow-600 dark:text-yellow-400">Analyse exploratoire</p>
          <p className="text-xs text-muted-foreground mt-1">
            Ces projections sont basées sur des modèles statistiques appliqués aux prix historiques.
            Elles ne constituent pas des conseils d'investissement. Les marchés crypto sont hautement
            imprévisibles — aucun modèle ne peut prédire l'avenir de manière fiable.
          </p>
        </div>
      </div>

      {/* Bear market mode banner */}
      {marketCycle?.market_regime?.dominant_regime === 'bearish' && (marketCycle?.market_regime?.confidence ?? 0) > 0.5 && (
        <div className="rounded-lg border-2 border-red-500/40 bg-red-500/5 p-4 flex items-start gap-3">
          <ShieldAlert className="h-6 w-6 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-bold text-red-600 dark:text-red-400 flex items-center gap-2">
              Mode marché baissier actif
              <Badge variant="destructive" className="text-xs">
                Confiance {((marketCycle?.market_regime?.confidence ?? 0) * 100).toFixed(0)}%
              </Badge>
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Les projections tiennent compte du régime baissier détecté.
              Les prédictions haussières ont été atténuées et les intervalles de confiance élargis.
              Privilégiez la prudence et le DCA progressif.
            </p>
          </div>
        </div>
      )}

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Analyse & Projections</h1>
          <p className="text-muted-foreground">Projections statistiques et sentiment de marché</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={daysAhead <= 7 ? 'default' : daysAhead <= 14 ? 'secondary' : 'outline'} className="text-xs">
            Confiance : {daysAhead <= 7 ? 'Haute' : daysAhead <= 14 ? 'Modérée' : 'Indicative'}
          </Badge>
          <Select value={daysAhead.toString()} onValueChange={(v) => setDaysAhead(parseInt(v))}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7j — Court terme</SelectItem>
              <SelectItem value="14">14j — Moyen terme</SelectItem>
              <SelectItem value="30">30j — Tendance</SelectItem>
            </SelectContent>
          </Select>
        </div>
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
                  {totalAlerts} {totalAlerts > 1 ? 'signaux' : 'signal'}
                </Badge>
              )}
            </div>
            {sentimentError ? (
              <p className="text-center text-sm text-muted-foreground py-4">Impossible de charger le sentiment</p>
            ) : (
              <>
                <div className="flex items-center justify-center">
                  <FearGreedGauge value={sentiment?.fear_greed_index ?? 50} thresholds={dt.fear_greed} />
                </div>
                <div className="flex items-center justify-center gap-3 mt-3">
                  <Badge variant={
                    sentiment?.overall_sentiment === 'bullish' ? 'default' :
                    sentiment?.overall_sentiment === 'bearish' ? 'destructive' : 'secondary'
                  }>
                    {sentiment?.overall_sentiment === 'bullish' ? 'Haussier' :
                     sentiment?.overall_sentiment === 'bearish' ? 'Baissier' :
                     sentiment?.overall_sentiment === 'neutral' ? 'Neutre' :
                     sentiment?.overall_sentiment ?? 'N/A'}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {{ markup: 'Expansion', markdown: 'Contraction', accumulation: 'Accumulation', distribution: 'Distribution' }[sentiment?.market_phase ?? ''] ?? sentiment?.market_phase ?? ''}
                  </span>
                </div>
              </>
            )}
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
                  {(() => {
                    const total = summary.bullish_assets + summary.neutral_assets + summary.bearish_assets
                    return total > 0 ? (
                      <div className="flex h-3 rounded-full overflow-hidden bg-muted">
                        {summary.bullish_assets > 0 && (
                          <div
                            className="bg-green-500 transition-all"
                            style={{ width: `${(summary.bullish_assets / total) * 100}%` }}
                          />
                        )}
                        {summary.neutral_assets > 0 && (
                          <div
                            className="bg-yellow-500 transition-all"
                            style={{ width: `${(summary.neutral_assets / total) * 100}%` }}
                          />
                        )}
                        {summary.bearish_assets > 0 && (
                          <div
                            className="bg-red-500 transition-all"
                            style={{ width: `${(summary.bearish_assets / total) * 100}%` }}
                          />
                        )}
                      </div>
                    ) : (
                      <div className="flex h-3 rounded-full overflow-hidden bg-muted" />
                    )
                  })()}
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
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="predictions" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Projections
          </TabsTrigger>
          <TabsTrigger value="cycles" className="flex items-center gap-2">
            <Repeat className="h-4 w-4" />
            Cycles
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

        {/* ── Tab: Projections ── */}
        <TabsContent value="predictions">
          <Card>
            <CardHeader>
              <CardTitle>Projections par actif</CardTitle>
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
                          <th className="text-center py-3 px-4 font-medium">Fiabilité</th>
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
                                <div className="flex items-center gap-2">
                                  <div>
                                    <p className="font-medium">{pred.symbol}</p>
                                    {pred.name && pred.name !== pred.symbol && (
                                      <p className="text-xs text-muted-foreground">{pred.name}</p>
                                    )}
                                  </div>
                                  {pred.model_used === 'random_walk' && (
                                    <TooltipProvider>
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                        </TooltipTrigger>
                                        <TooltipContent>
                                          <p className="text-xs">Données historiques insuffisantes — prédiction dégradée</p>
                                        </TooltipContent>
                                      </Tooltip>
                                    </TooltipProvider>
                                  )}
                                </div>
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
                                  <ReliabilityScore reliabilityScore={pred.reliability_score} skillScore={pred.skill_score} hitRate={pred.hit_rate} hitRateSignificant={pred.hit_rate_significant} hitRateN={pred.hit_rate_n_samples} modelConfidence={pred.model_confidence} />
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

                  {/* Expanded asset detail */}
                  {selectedPrediction && chartData.length > 0 && (
                    <div className="mt-6 pt-6 border-t">
                      <h4 className="font-medium mb-1">
                        Projection {selectedPrediction.symbol} — {daysAhead} jours
                      </h4>

                      {/* Prix actuel → prédit + trend strength */}
                      <div className="flex flex-wrap items-center gap-4 mb-3">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="text-muted-foreground">Actuel:</span>
                          <span className="font-bold">{formatCurrency(selectedPrediction.current_price)}</span>
                          <span className="text-muted-foreground">→</span>
                          <span className={`font-bold ${selectedPrediction.change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {formatCurrency(selectedPrediction.predicted_price)}
                          </span>
                          <span className={`text-xs ${selectedPrediction.change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            ({selectedPrediction.change_percent >= 0 ? '+' : ''}{selectedPrediction.change_percent.toFixed(2)}%)
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">Force:</span>
                          <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                selectedPrediction.trend_strength > dt.trend_strength.strong ? 'bg-green-500' :
                                selectedPrediction.trend_strength > dt.trend_strength.moderate ? 'bg-yellow-500' : 'bg-gray-400'
                              }`}
                              style={{ width: `${Math.min(100, selectedPrediction.trend_strength)}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium">{selectedPrediction.trend_strength.toFixed(0)}%</span>
                        </div>
                      </div>

                      {/* Model disagreement warning */}
                      {selectedPrediction.models_agree === false && (
                        <div className="mb-3 flex items-start gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20">
                          <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                          <p className="text-xs text-amber-600 dark:text-amber-400">
                            Les modèles divergent sur la direction — fiabilité réduite
                          </p>
                        </div>
                      )}

                      {selectedPrediction.regime_info?.regime_price_adjustment && (
                        <div className="mb-3 flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                          <ShieldAlert className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-sm font-semibold text-red-600 dark:text-red-400">
                              Correction régime appliquée
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Le régime de marché (
                              {{ bullish: 'haussier', bearish: 'baissier', top: 'sommet', bottom: 'creux' }[
                                selectedPrediction.regime_info.dominant_regime
                              ] || selectedPrediction.regime_info.dominant_regime}
                              , confiance {(selectedPrediction.regime_info.confidence * 100).toFixed(0)}%)
                              contredit la prédiction des modèles. La projection a été ajustée de{' '}
                              {((selectedPrediction.regime_info.adjustment_factor ?? 0) * 100).toFixed(0)}%
                              vers une direction plus prudente.
                            </p>
                          </div>
                        </div>
                      )}

                      <p className="text-sm text-muted-foreground mb-2">
                        Support: {formatCurrency(selectedPrediction.support_level)} · Résistance: {formatCurrency(selectedPrediction.resistance_level)}
                      </p>
                      {/* Show Reality toggle + Backtest MAPE */}
                      <div className="flex items-center gap-3 mb-4">
                        <Button
                          variant={showReality ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setShowReality(!showReality)}
                          className="gap-2"
                        >
                          {loadingBacktest ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : showReality ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                          {showReality ? 'Masquer la réalité' : 'Afficher la réalité'}
                        </Button>
                        {showReality && backtestData && (
                          <div className="flex items-center gap-2">
                            {backtestData.overall_mape != null && (
                              <Badge variant={backtestData.needs_retraining ? 'destructive' : 'secondary'} className="text-xs">
                                MAPE : {backtestData.overall_mape.toFixed(1)}%
                              </Badge>
                            )}
                            {backtestData.overall_direction_accuracy != null && (
                              <Badge variant="outline" className="text-xs">
                                Direction : {backtestData.overall_direction_accuracy.toFixed(0)}%
                              </Badge>
                            )}
                            {backtestData.needs_retraining && (
                              <span className="text-xs text-red-500 font-medium">
                                Modèle en cours de réentraînement
                              </span>
                            )}
                          </div>
                        )}
                      </div>

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
                        <div className="flex items-center gap-2 mb-4">
                          <p className="text-xs text-muted-foreground">Modèle: {selectedPrediction.model_used}</p>
                          {selectedPrediction.model_used === 'random_walk' && (
                            <Badge variant="outline" className="text-xs text-amber-500 border-amber-500/30">
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              Données insuffisantes
                            </Badge>
                          )}
                        </div>
                      )}
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart data={chartData}>
                            <defs>
                              <linearGradient id="confGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                            <YAxis
                              domain={[
                                (dataMin: number) => {
                                  const prices = chartData.flatMap(d => [
                                    d.confidence_high, d.confidence_low, d.actual,
                                  ].filter((v): v is number => v != null))
                                  const min = prices.length > 0 ? Math.min(...prices) : dataMin
                                  const max = prices.length > 0 ? Math.max(...prices) : dataMin
                                  const range = max - min || min * 0.1
                                  return Math.max(0, min - range * 0.1)
                                },
                                (dataMax: number) => {
                                  const prices = chartData.flatMap(d => [
                                    d.confidence_high, d.confidence_low, d.actual,
                                  ].filter((v): v is number => v != null))
                                  const max = prices.length > 0 ? Math.max(...prices) : dataMax
                                  const min = prices.length > 0 ? Math.min(...prices) : dataMax
                                  const range = max - min || max * 0.1
                                  return max + range * 0.1
                                },
                              ]}
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
                                  actual: 'Prix réel',
                                  predicted_past: 'Prédiction passée',
                                }
                                return [formatCurrency(value), labels[name] || name]
                              }}
                            />
                            <Area type="monotone" dataKey="confidence_high" stroke="none" fill="url(#confGradient)" fillOpacity={1} />
                            <Area type="monotone" dataKey="confidence_low" stroke="none" fill="hsl(var(--background))" fillOpacity={1} />
                            <Line type="monotone" dataKey="price" stroke="#3b82f6" strokeWidth={2} strokeDasharray="6 3" dot={false} connectNulls />
                            {/* Reality overlay: actual prices (solid green, matching Dashboard) */}
                            {showReality && (
                              <>
                                <Line type="monotone" dataKey="actual" stroke="#22c55e" strokeWidth={2.5} dot={{ r: 3, fill: '#22c55e' }} connectNulls />
                                <Line type="monotone" dataKey="predicted_past" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls />
                              </>
                            )}
                            {showSupportResistance && (
                              <>
                                <ReferenceLine y={selectedPrediction.support_level} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Support', position: 'left', fontSize: 10, fill: '#ef4444' }} />
                                <ReferenceLine y={selectedPrediction.resistance_level} stroke="#10b981" strokeDasharray="4 4" label={{ value: 'Résistance', position: 'left', fontSize: 10, fill: '#10b981' }} />
                              </>
                            )}
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>

                      {/* Chart legend when reality is shown */}
                      {showReality && (
                        <div className="flex items-center justify-center gap-4 mt-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1.5">
                            <span className="w-4 h-0.5 bg-[#22c55e] inline-block rounded" />
                            Prix réel
                          </span>
                          <span className="flex items-center gap-1.5">
                            <span className="w-4 h-0.5 bg-[#3b82f6] inline-block rounded" style={{ borderTop: '2px dashed #3b82f6', height: 0 }} />
                            Prix prédit
                          </span>
                          <span className="flex items-center gap-1.5">
                            <span className="w-4 h-0.5 bg-[#94a3b8] inline-block rounded" />
                            Prédiction passée
                          </span>
                        </div>
                      )}

                      {/* Recommendation */}
                      {selectedPrediction.recommendation && (
                        <div className="mt-4 p-4 rounded-lg bg-primary/5 border border-primary/10">
                          <div className="flex items-center gap-2 mb-2">
                            <Target className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">Recommandation</span>
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed">
                            {selectedPrediction.recommendation}
                          </p>
                        </div>
                      )}

                      {/* SHAP Explanations */}
                      {selectedPrediction.explanations && selectedPrediction.explanations.length > 0 && (() => {
                        const explanations = selectedPrediction.explanations
                        const maxImportance = Math.max(...explanations.map(e => e.importance))
                        return (
                        <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
                          <div className="flex items-center gap-2 mb-3">
                            <Brain className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">Facteurs clés de la prédiction</span>
                          </div>
                          <div className="space-y-2">
                            {explanations.map((exp, i) => {
                              const isUp = exp.direction === 'hausse'
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
                        )
                      })()}

                      {/* Regime Info + Multi-Timeframe + Liquidity */}
                      {selectedPrediction.regime_info && (() => {
                        const ri = selectedPrediction.regime_info
                        const regimeColors: Record<string, string> = {
                          bullish: 'text-green-500 bg-green-500/10',
                          bearish: 'text-red-500 bg-red-500/10',
                          top: 'text-amber-500 bg-amber-500/10',
                          bottom: 'text-blue-500 bg-blue-500/10',
                          neutral: 'text-gray-500 bg-gray-500/10',
                        }
                        const regimeLabels: Record<string, string> = {
                          bullish: 'Haussier',
                          bearish: 'Baissier',
                          top: 'Sommet',
                          bottom: 'Creux',
                          neutral: 'Neutre',
                        }
                        const regimeClass = regimeColors[ri.dominant_regime] || regimeColors.neutral
                        return (
                          <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
                            <div className="flex items-center gap-2 mb-3">
                              <Activity className="h-4 w-4 text-primary" />
                              <span className="text-sm font-medium">Régime de marché</span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-3">
                              <Badge className={regimeClass}>
                                {regimeLabels[ri.dominant_regime] || ri.dominant_regime}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                Confiance: {(ri.confidence * 100).toFixed(0)}%
                              </span>
                              {ri.timeframe_alignment && (
                                <Badge variant={ri.timeframe_alignment === 'aligned' ? 'outline' : 'destructive'} className="text-xs gap-1">
                                  <Layers className="h-3 w-3" />
                                  {ri.timeframe_alignment === 'aligned' ? 'Daily/Weekly alignés' : 'Daily/Weekly divergents'}
                                </Badge>
                              )}
                              {ri.weekly_regime && ri.weekly_regime !== ri.dominant_regime && (
                                <span className="text-xs text-muted-foreground">
                                  Weekly: {regimeLabels[ri.weekly_regime] || ri.weekly_regime}
                                </span>
                              )}
                            </div>

                            {/* Probability bars */}
                            {ri.probabilities && (
                              <div className="space-y-1.5 mb-3">
                                {Object.entries(ri.probabilities)
                                  .sort(([, a], [, b]) => b - a)
                                  .map(([regime, prob]) => (
                                    <div key={regime} className="flex items-center gap-2">
                                      <span className="text-xs w-16 text-muted-foreground capitalize">{regimeLabels[regime] || regime}</span>
                                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                        <div
                                          className={`h-full rounded-full ${
                                            regime === 'bullish' ? 'bg-green-500' :
                                            regime === 'bearish' ? 'bg-red-500' :
                                            regime === 'top' ? 'bg-amber-500' :
                                            regime === 'bottom' ? 'bg-blue-500' : 'bg-gray-400'
                                          }`}
                                          style={{ width: `${(prob * 100).toFixed(0)}%` }}
                                        />
                                      </div>
                                      <span className="text-xs text-muted-foreground w-10 text-right">{(prob * 100).toFixed(0)}%</span>
                                    </div>
                                  ))}
                              </div>
                            )}

                            {ri.note && (
                              <p className="text-xs text-muted-foreground">{ri.note}</p>
                            )}

                            {/* Liquidity Warning */}
                            {ri.liquidity_warning && (
                              <div className="mt-2 flex items-start gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20">
                                <Droplets className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                                <p className="text-xs text-amber-600 dark:text-amber-400">{ri.liquidity_warning}</p>
                              </div>
                            )}
                          </div>
                        )
                      })()}

                      {/* Track Record */}
                      <TrackRecordPanel symbol={selectedPrediction.symbol} />
                    </div>
                  )}
                </>
              ) : (
                <p className="text-center text-muted-foreground py-8">Aucune prédiction disponible</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab: Cycles de Marché ── */}
        <TabsContent value="cycles" className="space-y-4">
          {loadingCycle ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : marketCycle ? (
            <>
              {/* Row 1: Cycle gauge + BTC regime + Portfolio regime */}
              <div className="grid gap-4 lg:grid-cols-3">
                {/* Cycle Position */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Repeat className="h-4 w-4 text-primary" />
                      Position dans le cycle
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CycleGauge
                      position={marketCycle.cycle_position}
                    />
                    <div className="flex justify-center gap-3 mt-2">
                      {marketCycle.fear_greed != null && (
                        <span className="text-xs text-muted-foreground">
                          Fear & Greed: <span className="font-medium">{marketCycle.fear_greed}</span>
                        </span>
                      )}
                      {marketCycle.btc_dominance != null && (
                        <span className="text-xs text-muted-foreground">
                          BTC Dom: <span className="font-medium">{marketCycle.btc_dominance}%</span>
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* BTC Market Regime */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Activity className="h-4 w-4 text-primary" />
                      Régime BTC (référence)
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {marketCycle.market_regime ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <Badge className={
                            marketCycle.market_regime.dominant_regime === 'bullish' ? 'bg-green-500/10 text-green-500' :
                            marketCycle.market_regime.dominant_regime === 'bearish' ? 'bg-red-500/10 text-red-500' :
                            marketCycle.market_regime.dominant_regime === 'top' ? 'bg-amber-500/10 text-amber-500' :
                            marketCycle.market_regime.dominant_regime === 'bottom' ? 'bg-blue-500/10 text-blue-500' :
                            'bg-gray-500/10 text-gray-500'
                          }>
                            {{ bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux' }[marketCycle.market_regime.dominant_regime] || marketCycle.market_regime.dominant_regime}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            Confiance: {(marketCycle.market_regime.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          {Object.entries(marketCycle.market_regime.probabilities)
                            .sort(([, a], [, b]) => b - a)
                            .map(([phase, prob]) => (
                              <div key={phase} className="flex items-center gap-2">
                                <span className="text-xs w-14 text-muted-foreground capitalize">
                                  {{ bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux' }[phase] || phase}
                                </span>
                                <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                  <div
                                    className={`h-full rounded-full ${
                                      phase === 'bullish' ? 'bg-green-500' :
                                      phase === 'bearish' ? 'bg-red-500' :
                                      phase === 'top' ? 'bg-amber-500' :
                                      'bg-blue-500'
                                    }`}
                                    style={{ width: `${(prob * 100).toFixed(1)}%` }}
                                  />
                                </div>
                                <span className="text-xs text-muted-foreground w-10 text-right">{(prob * 100).toFixed(1)}%</span>
                              </div>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">{marketCycle.market_regime.description}</p>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-4">Données indisponibles</p>
                    )}
                  </CardContent>
                </Card>

                {/* Portfolio Regime */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-primary" />
                      Régime portefeuille
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {marketCycle.portfolio_regime ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Badge className={
                          marketCycle.portfolio_regime.dominant_regime === 'bullish' ? 'bg-green-500/10 text-green-500' :
                          marketCycle.portfolio_regime.dominant_regime === 'bearish' ? 'bg-red-500/10 text-red-500' :
                          marketCycle.portfolio_regime.dominant_regime === 'top' ? 'bg-amber-500/10 text-amber-500' :
                          marketCycle.portfolio_regime.dominant_regime === 'bottom' ? 'bg-blue-500/10 text-blue-500' :
                          'bg-gray-500/10 text-gray-500'
                        }>
                          {{ bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux' }[marketCycle.portfolio_regime.dominant_regime] || marketCycle.portfolio_regime.dominant_regime}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {marketCycle.per_asset.length} actif{marketCycle.per_asset.length > 1 ? 's' : ''} analysé{marketCycle.per_asset.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {Object.entries(marketCycle.portfolio_regime.probabilities)
                          .sort(([, a], [, b]) => b - a)
                          .map(([phase, prob]) => (
                            <div key={phase} className="flex items-center gap-2">
                              <span className="text-xs w-14 text-muted-foreground capitalize">
                                {{ bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux' }[phase] || phase}
                              </span>
                              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    phase === 'bullish' ? 'bg-green-500' :
                                    phase === 'bearish' ? 'bg-red-500' :
                                    phase === 'top' ? 'bg-amber-500' :
                                    'bg-blue-500'
                                  }`}
                                  style={{ width: `${(prob * 100).toFixed(1)}%` }}
                                />
                              </div>
                              <span className="text-xs text-muted-foreground w-10 text-right">{(prob * 100).toFixed(1)}%</span>
                            </div>
                          ))}
                      </div>
                    </div>
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-4">Données indisponibles</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Row 2: Time-to-Pivot + Distribution Diagnostic */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* Time-to-Pivot */}
                {marketCycle.time_to_pivot && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Clock className="h-4 w-4 text-primary" />
                        Time-to-Pivot
                      </CardTitle>
                      <CardDescription>Estimation du prochain changement de phase</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <Badge variant="outline" className={
                              marketCycle.time_to_pivot.current_phase === 'Euphorie' ? 'text-red-500 border-red-500/30' :
                              marketCycle.time_to_pivot.current_phase === 'Distribution' ? 'text-amber-500 border-amber-500/30' :
                              marketCycle.time_to_pivot.current_phase === 'Expansion' ? 'text-green-500 border-green-500/30' :
                              marketCycle.time_to_pivot.current_phase === 'Accumulation' ? 'text-cyan-500 border-cyan-500/30' :
                              'text-blue-500 border-blue-500/30'
                            }>
                              {marketCycle.time_to_pivot.current_phase}
                            </Badge>
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            <Badge variant="outline" className={
                              marketCycle.time_to_pivot.next_phase === 'Euphorie' ? 'text-red-500 border-red-500/30' :
                              marketCycle.time_to_pivot.next_phase === 'Distribution' ? 'text-amber-500 border-amber-500/30' :
                              marketCycle.time_to_pivot.next_phase === 'Expansion' ? 'text-green-500 border-green-500/30' :
                              marketCycle.time_to_pivot.next_phase === 'Accumulation' ? 'text-cyan-500 border-cyan-500/30' :
                              'text-blue-500 border-blue-500/30'
                            }>
                              {marketCycle.time_to_pivot.next_phase}
                            </Badge>
                          </div>
                          <div className="flex items-baseline gap-1">
                            <span className="text-3xl font-bold tabular-nums">~{marketCycle.time_to_pivot.estimated_days}</span>
                            <span className="text-sm text-muted-foreground">jours</span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">
                            Phase {marketCycle.time_to_pivot.next_phase} prévue dans ~{marketCycle.time_to_pivot.estimated_days} jours
                          </p>
                        </div>
                        <div className="text-center">
                          <div className="w-12 h-12 rounded-full border-2 flex items-center justify-center" style={{
                            borderColor: marketCycle.time_to_pivot.confidence >= 0.6 ? '#22c55e' :
                              marketCycle.time_to_pivot.confidence >= 0.35 ? '#eab308' : '#ef4444',
                          }}>
                            <span className="text-xs font-bold" style={{
                              color: marketCycle.time_to_pivot.confidence >= 0.6 ? '#22c55e' :
                                marketCycle.time_to_pivot.confidence >= 0.35 ? '#eab308' : '#ef4444',
                            }}>
                              {(marketCycle.time_to_pivot.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <span className="text-[10px] text-muted-foreground">Confiance</span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Distribution Diagnostic */}
                {marketCycle.distribution_diagnostic && marketCycle.distribution_diagnostic.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Flame className="h-4 w-4 text-amber-500" />
                        Diagnostic Distribution
                      </CardTitle>
                      <CardDescription>Actifs en zone de distribution — signaux de vente potentiels</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {marketCycle.distribution_diagnostic.map((diag) => (
                          <div
                            key={diag.symbol}
                            className={`p-3 rounded-lg border ${
                              diag.sell_priority === 'high' ? 'border-red-500/30 bg-red-500/5' :
                              diag.sell_priority === 'medium' ? 'border-amber-500/30 bg-amber-500/5' :
                              'border-muted bg-muted/20'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium">{diag.symbol}</span>
                                <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                                  diag.sell_priority === 'high' ? 'text-red-500 border-red-500/30' :
                                  diag.sell_priority === 'medium' ? 'text-amber-500 border-amber-500/30' :
                                  'text-gray-500'
                                }`}>
                                  {diag.sell_priority === 'high' ? 'Vente prioritaire' :
                                   diag.sell_priority === 'medium' ? 'Surveillance' : 'Faible'}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                {diag.rsi !== null && (
                                  <span>RSI: <span className={diag.rsi > 70 ? 'text-red-500 font-medium' : ''}>{diag.rsi}</span></span>
                                )}
                                <span>Poids: {diag.weight_pct}%</span>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {diag.signals.map((sig, i) => (
                                <Badge key={i} variant="secondary" className="text-[10px]">{sig}</Badge>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Row 3: Top / Bottom Estimates */}
              {marketCycle.top_bottom_estimates && (
                <TopBottomCard estimates={marketCycle.top_bottom_estimates} />
              )}

              {/* Row 3: Technical Indicators */}
              {marketCycle.market_signals.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Brain className="h-4 w-4 text-primary" />
                      Indicateurs techniques (BTC)
                    </CardTitle>
                    <CardDescription>7 indicateurs analysés pour détecter le régime de marché</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {marketCycle.market_signals.map((sig) => {
                        const sigColor =
                          sig.signal === 'bullish' ? 'border-green-500/30 bg-green-500/5' :
                          sig.signal === 'bearish' ? 'border-red-500/30 bg-red-500/5' :
                          sig.signal === 'top' ? 'border-amber-500/30 bg-amber-500/5' :
                          sig.signal === 'bottom' ? 'border-blue-500/30 bg-blue-500/5' :
                          'border-muted bg-muted/20'
                        const sigLabel =
                          sig.signal === 'bullish' ? 'Haussier' :
                          sig.signal === 'bearish' ? 'Baissier' :
                          sig.signal === 'top' ? 'Sommet' :
                          sig.signal === 'bottom' ? 'Creux' : 'Neutre'
                        const sigTextColor =
                          sig.signal === 'bullish' ? 'text-green-500' :
                          sig.signal === 'bearish' ? 'text-red-500' :
                          sig.signal === 'top' ? 'text-amber-500' :
                          sig.signal === 'bottom' ? 'text-blue-500' : 'text-gray-500'

                        return (
                          <div key={sig.name} className={`p-3 rounded-lg border ${sigColor}`}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium truncate">{sig.name}</span>
                              <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${sigTextColor}`}>
                                {sigLabel}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2 mb-1.5">
                              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    sig.signal === 'bullish' ? 'bg-green-500' :
                                    sig.signal === 'bearish' ? 'bg-red-500' :
                                    sig.signal === 'top' ? 'bg-amber-500' :
                                    sig.signal === 'bottom' ? 'bg-blue-500' : 'bg-gray-400'
                                  }`}
                                  style={{ width: `${(sig.strength * 100).toFixed(0)}%` }}
                                />
                              </div>
                              <span className="text-[10px] text-muted-foreground w-8 text-right">
                                {(sig.strength * 100).toFixed(0)}%
                              </span>
                            </div>
                            <p className="text-[10px] text-muted-foreground leading-tight">{sig.description}</p>
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Row 3: Per-asset regime */}
              {marketCycle.per_asset.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Layers className="h-4 w-4 text-primary" />
                      Régime par actif
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                            <th className="text-center py-2 px-3 text-xs font-medium">Régime</th>
                            <th className="text-center py-2 px-3 text-xs font-medium">Confiance</th>
                            <th className="text-left py-2 px-3 text-xs font-medium">Probabilités</th>
                          </tr>
                        </thead>
                        <tbody>
                          {marketCycle.per_asset.map((asset) => (
                            <tr key={asset.symbol} className="border-b last:border-0">
                              <td className="py-2 px-3">
                                <div>
                                  <span className="text-sm font-medium">{asset.symbol}</span>
                                  {asset.name && asset.name !== asset.symbol && (
                                    <span className="text-xs text-muted-foreground ml-2">{asset.name}</span>
                                  )}
                                </div>
                              </td>
                              <td className="py-2 px-3 text-center">
                                <Badge className={
                                  asset.dominant_regime === 'bullish' ? 'bg-green-500/10 text-green-500' :
                                  asset.dominant_regime === 'bearish' ? 'bg-red-500/10 text-red-500' :
                                  asset.dominant_regime === 'top' ? 'bg-amber-500/10 text-amber-500' :
                                  asset.dominant_regime === 'bottom' ? 'bg-blue-500/10 text-blue-500' :
                                  'bg-gray-500/10 text-gray-500'
                                } variant="outline">
                                  {{ bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux' }[asset.dominant_regime] || asset.dominant_regime}
                                </Badge>
                              </td>
                              <td className="py-2 px-3 text-center text-xs">
                                {(asset.confidence * 100).toFixed(0)}%
                              </td>
                              <td className="py-2 px-3">
                                <div className="flex h-2 rounded-full overflow-hidden bg-muted w-32">
                                  {Object.entries(asset.probabilities)
                                    .sort(([, a], [, b]) => b - a)
                                    .map(([phase, prob]) => (
                                      <div
                                        key={phase}
                                        className={
                                          phase === 'bullish' ? 'bg-green-500' :
                                          phase === 'bearish' ? 'bg-red-500' :
                                          phase === 'top' ? 'bg-amber-500' :
                                          'bg-blue-500'
                                        }
                                        style={{ width: `${(prob * 100).toFixed(0)}%` }}
                                        title={`${phase}: ${(prob * 100).toFixed(0)}%`}
                                      />
                                    ))}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Row 4: Advice */}
              {marketCycle.cycle_advice.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Target className="h-4 w-4 text-primary" />
                      Conseils adaptés au cycle
                    </CardTitle>
                    <CardDescription>Recommandations basées sur la phase de marché actuelle</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {marketCycle.cycle_advice.map((adv, i) => (
                        <div
                          key={i}
                          className={`p-4 rounded-lg border ${
                            adv.priority === 'high' ? 'border-primary/30 bg-primary/5' :
                            'border-muted bg-muted/20'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant={adv.priority === 'high' ? 'default' : 'secondary'} className="text-[10px]">
                              {adv.action}
                            </Badge>
                            <span className="text-sm font-medium">{adv.title}</span>
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed">{adv.description}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Market events → see CalendarPage */}
            </>
          ) : (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-muted-foreground">Impossible de charger l'analyse de cycle</p>
              </CardContent>
            </Card>
          )}
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
                          <span className="text-xs text-muted-foreground capitalize">
                            {{ support_break: 'cassure support', breakout: 'cassure résistance', strong_trend: 'tendance forte', opportunity: 'opportunité', info: 'information', buy: 'achat', sell: 'vente' }[alert.type] || alert.type.replace('_', ' ')}
                          </span>
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

          {/* Anomalies (in Signals tab) */}
          {anomaliesError && (
            <Card className="border-yellow-500/20">
              <CardContent className="py-6 text-center">
                <AlertTriangle className="h-8 w-8 mx-auto text-yellow-500 mb-2" />
                <p className="text-sm text-muted-foreground">Impossible de charger les anomalies</p>
              </CardContent>
            </Card>
          )}
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
                            <SelectItem key={p.symbol} value={p.symbol}>{p.symbol}{p.name && p.name !== p.symbol ? ` - ${p.name}` : ''}</SelectItem>
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
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {[
                          { label: 'Crash', value: -50, color: 'bg-red-500/10 text-red-500 hover:bg-red-500/20' },
                          { label: 'Bear', value: -30, color: 'bg-red-500/10 text-red-400 hover:bg-red-500/20' },
                          { label: 'Correction', value: -15, color: 'bg-orange-500/10 text-orange-500 hover:bg-orange-500/20' },
                          { label: 'Rebond', value: 20, color: 'bg-green-500/10 text-green-500 hover:bg-green-500/20' },
                          { label: 'Bull', value: 50, color: 'bg-green-500/10 text-green-400 hover:bg-green-500/20' },
                          { label: 'Moon', value: 100, color: 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20' },
                        ].map((scenario) => (
                          <button
                            key={scenario.value}
                            onClick={() => {
                              setWhatIfChange(scenario.value)
                              setTimeout(runWhatIf, 50)
                            }}
                            className={`text-xs px-2.5 py-1 rounded-full border cursor-pointer transition-colors ${scenario.color} ${whatIfChange === scenario.value ? 'ring-1 ring-primary' : ''}`}
                          >
                            {scenario.label} ({scenario.value > 0 ? '+' : ''}{scenario.value}%)
                          </button>
                        ))}
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="100"
                        value={whatIfChange}
                        onChange={(e) => setWhatIfChange(parseInt(e.target.value))}
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

                  {whatIfResult && whatIfResult.per_asset.length > 0 && (() => {
                    const STABLECOINS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'FDUSD', 'PYUSD']
                    const filteredAssets = whatIfResult.per_asset.filter(
                      a => !STABLECOINS.includes(a.symbol.toUpperCase()) || Math.abs(a.impact) > 0.01
                    )
                    return filteredAssets.length > 0 ? (
                      <div>
                        <p className="text-sm font-medium mb-2">Impact par actif</p>
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              data={filteredAssets.map(a => ({ name: a.symbol, impact: a.impact }))}
                              layout="vertical"
                            >
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis type="number" tickFormatter={(v) => formatCurrency(v).replace('€', '')} />
                              <YAxis type="category" dataKey="name" width={50} tick={{ fontSize: 12 }} />
                              <RechartsTooltip formatter={(value: number) => formatCurrency(value)} />
                              <Bar dataKey="impact" radius={4}>
                                {filteredAssets.map((a, i) => (
                                  <Cell key={i} fill={a.impact >= 0 ? '#10b981' : '#ef4444'} />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    ) : null
                  })()}
                </div>
              ) : (
                <p className="text-center text-muted-foreground py-8">Aucun actif disponible</p>
              )}
            </CardContent>
          </Card>

        </TabsContent>
      </Tabs>

    </div>
  )
}
