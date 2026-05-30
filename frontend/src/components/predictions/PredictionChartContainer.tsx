import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import type { DisplayThresholds } from '@/types'
import type {
  PortfolioPrediction,
  BacktestData,
  ChartPoint,
  TrackRecordData,
} from '@/types/predictions'
import {
  AlertTriangle,
  Brain,
  Loader2,
  ArrowUp,
  ArrowDown,
  Minus,
  ShieldAlert,
  Target,
  Activity,
  Droplets,
  Layers,
  Eye,
  EyeOff,
  History,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'

// ── Regime labels/colors (shared) ────────────────────────────────────

const REGIME_LABELS: Record<string, string> = {
  bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux', neutral: 'Neutre',
}
const REGIME_COLORS: Record<string, string> = {
  bullish: 'text-gain bg-gain/10',
  bearish: 'text-loss bg-loss/10',
  top: 'text-warning bg-warning/10',
  bottom: 'text-accent bg-accent/10',
  neutral: 'text-gray-500 bg-gray-500/10',
}
const REGIME_BAR_COLORS: Record<string, string> = {
  bullish: 'bg-gain', bearish: 'bg-loss', top: 'bg-warning', bottom: 'bg-accent',
}

// ── Track Record Panel ───────────────────────────────────────────────

const TrackRecordPanel = React.memo(({ symbol }: { symbol: string }) => {
  const { data, isLoading } = useQuery<TrackRecordData>({
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
  const mapeColor = s.avg_mape != null ? (s.avg_mape <= 5 ? 'text-gain' : s.avg_mape <= 10 ? 'text-warning' : 'text-loss') : 'text-muted-foreground'
  const dirColor = s.direction_accuracy != null ? (s.direction_accuracy >= 60 ? 'text-gain' : s.direction_accuracy >= 50 ? 'text-warning' : 'text-loss') : 'text-muted-foreground'
  const ciColor = s.ci_coverage != null ? (s.ci_coverage >= 90 ? 'text-gain' : s.ci_coverage >= 70 ? 'text-warning' : 'text-loss') : 'text-muted-foreground'

  return (
    <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
      <div className="flex items-center gap-2 mb-3">
        <History className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Track Record</span>
        <Badge variant="outline" className="text-[10px] ml-auto">{s.total_checked} prédictions vérifiées</Badge>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Erreur moy.</p>
          <p className={`text-sm font-bold ${mapeColor}`}>{s.avg_mape != null ? `${s.avg_mape.toFixed(1)}%` : 'N/A'}</p>
          <p className="text-[10px] text-muted-foreground">MAPE</p>
        </div>
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Direction</p>
          <p className={`text-sm font-bold ${dirColor}`}>{s.direction_accuracy != null ? `${s.direction_accuracy.toFixed(0)}%` : 'N/A'}</p>
          <p className="text-[10px] text-muted-foreground">précision</p>
        </div>
        <div className="text-center p-2 rounded bg-background">
          <p className="text-[10px] text-muted-foreground">Couverture IC</p>
          <p className={`text-sm font-bold ${ciColor}`}>{s.ci_coverage != null ? `${s.ci_coverage.toFixed(0)}%` : 'N/A'}</p>
          <p className="text-[10px] text-muted-foreground">dans les bandes</p>
        </div>
      </div>
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
                    r.mape != null ? (r.mape <= 5 ? 'text-gain' : r.mape <= 10 ? 'text-warning' : 'text-loss') : ''
                  }`}>
                    {r.mape != null ? `${r.mape.toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    {r.direction_correct != null ? (
                      r.direction_correct ? (
                        <CheckCircle className="h-3 w-3 text-gain mx-auto" />
                      ) : (
                        <XCircle className="h-3 w-3 text-loss mx-auto" />
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
})
TrackRecordPanel.displayName = 'TrackRecordPanel'

// ── Main Chart Container ─────────────────────────────────────────────

interface PredictionChartContainerProps {
  selectedPrediction: PortfolioPrediction
  chartData: ChartPoint[]
  showSupportResistance: boolean
  showReality: boolean
  setShowReality: (v: boolean) => void
  loadingBacktest: boolean
  backtestData?: BacktestData
  daysAhead: number
  dt: DisplayThresholds
  formatPrice: (v: number) => string
}

export default function PredictionChartContainer({
  selectedPrediction,
  chartData,
  showSupportResistance,
  showReality,
  setShowReality,
  loadingBacktest,
  backtestData,
  daysAhead,
  dt,
  formatPrice,
}: PredictionChartContainerProps) {
  const { theme, color } = useNivoTheme()

  const cConfidence = color('--chart-5')
  const cPrice = color('--chart-5')
  const cActual = color('--chart-3')
  const cPast = color('--muted-foreground')
  const cSupport = color('--chart-4')
  const cResistance = color('--chart-3')

  const { yMin, yMax } = (() => {
    const prices = chartData.flatMap((d) =>
      [d.confidence_high, d.confidence_low, d.actual, d.price].filter(
        (v): v is number => v != null
      )
    )
    if (prices.length === 0) return { yMin: 0, yMax: 100 }
    const min = Math.min(...prices)
    const max = Math.max(...prices)
    const range = max - min || max * 0.1 || 1
    return { yMin: Math.max(0, min - range * 0.1), yMax: max + range * 0.1 }
  })()

  const seriesFor = (key: 'price' | 'actual' | 'predicted_past' | 'confidence_high' | 'confidence_low') => ({
    id: key,
    data: chartData
      .filter((d) => (d as unknown as Record<string, number | null>)[key] != null)
      .map((d) => ({ x: d.date, y: (d as unknown as Record<string, number>)[key] })),
  })

  const series: LineSeries[] = [
    seriesFor('confidence_high'),
    seriesFor('confidence_low'),
    seriesFor('price'),
    ...(showReality ? [seriesFor('actual'), seriesFor('predicted_past')] : []),
  ]

  const tickValues = (() => {
    const dates = chartData.map((d) => d.date)
    const target = Math.min(6, dates.length)
    const step = Math.max(1, Math.floor(dates.length / target))
    return dates.filter((_, i) => i % step === 0)
  })()

  const SERIES_LABELS: Record<string, string> = {
    confidence_high: 'Borne haute',
    confidence_low: 'Borne basse',
    price: 'Prix prédit',
    actual: 'Prix réel',
    predicted_past: 'Prédiction passée',
  }

  // Confidence band (area between low and high), drawn beneath the lines.
  const BandLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
    const sx = xScale as (v: string) => number
    const sy = yScale as (v: number) => number
    const band = chartData.filter((d) => d.confidence_high != null && d.confidence_low != null)
    if (band.length < 2) return null
    const top = band.map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(d.date)},${sy(d.confidence_high as number)}`)
    const bottom = [...band]
      .reverse()
      .map((d) => `L${sx(d.date)},${sy(d.confidence_low as number)}`)
    return <path d={`${top.join(' ')} ${bottom.join(' ')} Z`} fill={cConfidence} fillOpacity={0.12} />
  }

  // All trend lines, drawn with per-series dash/dots that Nivo can't express natively.
  const LinesLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
    const sx = xScale as (v: string) => number
    const sy = yScale as (v: number) => number
    const path = (key: 'price' | 'actual' | 'predicted_past') =>
      chartData
        .filter((d) => (d as unknown as Record<string, number | null>)[key] != null)
        .map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(d.date)},${sy((d as unknown as Record<string, number>)[key])}`)
        .join(' ')
    return (
      <>
        <path d={path('price')} fill="none" stroke={cPrice} strokeWidth={2} strokeDasharray="6 3" />
        {showReality && (
          <>
            <path d={path('predicted_past')} fill="none" stroke={cPast} strokeWidth={1.5} strokeDasharray="4 3" />
            <path d={path('actual')} fill="none" stroke={cActual} strokeWidth={2.5} />
            {chartData
              .filter((d) => d.actual != null)
              .map((d) => (
                <circle key={d.date} cx={sx(d.date)} cy={sy(d.actual as number)} r={3} fill={cActual} />
              ))}
          </>
        )}
      </>
    )
  }

  // Horizontal support / resistance markers.
  const RefLinesLayer = ({ yScale, innerWidth }: CommonCustomLayerProps<LineSeries>) => {
    if (!showSupportResistance) return null
    const sy = yScale as (v: number) => number
    const line = (y: number, stroke: string, label: string) => (
      <g>
        <line x1={0} x2={innerWidth} y1={sy(y)} y2={sy(y)} stroke={stroke} strokeWidth={1} strokeDasharray="4 4" />
        <text x={4} y={sy(y) - 4} fontSize={10} fill={stroke}>
          {label}
        </text>
      </g>
    )
    return (
      <>
        {line(selectedPrediction.support_level, cSupport, 'Support')}
        {line(selectedPrediction.resistance_level, cResistance, 'Résistance')}
      </>
    )
  }

  return (
    <div className="mt-6 pt-6 border-t">
      <h4 className="font-medium mb-1">
        Projection {selectedPrediction.symbol} — {daysAhead} jours
      </h4>

      {/* Price current → predicted + trend strength */}
      <div className="flex flex-wrap items-center gap-4 mb-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Actuel:</span>
          <span className="font-bold">{formatCurrency(selectedPrediction.current_price)}</span>
          <span className="text-muted-foreground">→</span>
          <span className={`font-bold ${selectedPrediction.change_percent >= 0 ? 'text-gain' : 'text-loss'}`}>
            {formatCurrency(selectedPrediction.predicted_price)}
          </span>
          <span className={`text-xs ${selectedPrediction.change_percent >= 0 ? 'text-gain' : 'text-loss'}`}>
            ({selectedPrediction.change_percent >= 0 ? '+' : ''}{selectedPrediction.change_percent.toFixed(2)}%)
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Force:</span>
          <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${
                selectedPrediction.trend_strength > dt.trend_strength.strong ? 'bg-gain' :
                selectedPrediction.trend_strength > dt.trend_strength.moderate ? 'bg-warning' : 'bg-gray-400'
              }`}
              style={{ width: `${Math.min(100, selectedPrediction.trend_strength)}%` }}
            />
          </div>
          <span className="text-xs font-medium">{selectedPrediction.trend_strength.toFixed(0)}%</span>
        </div>
      </div>

      {/* Model disagreement warning */}
      {selectedPrediction.models_agree === false && (
        <div className="mb-3 flex items-start gap-2 p-2 rounded bg-warning/10 border border-warning/20">
          <AlertTriangle className="h-4 w-4 text-warning mt-0.5 shrink-0" />
          <p className="text-xs text-warning dark:text-warning">
            Les modèles divergent sur la direction — fiabilité réduite
          </p>
        </div>
      )}

      {selectedPrediction.regime_info?.regime_price_adjustment && (
        <div className="mb-3 flex items-start gap-2 p-3 rounded-lg bg-loss/10 border border-loss/20">
          <ShieldAlert className="h-5 w-5 text-loss mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-loss dark:text-loss">
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
              <span className="text-xs text-loss font-medium">
                Modèle en cours de réentraînement
              </span>
            )}
          </div>
        )}
      </div>

      {/* Models detail badges */}
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
                  <ArrowUp className="h-3 w-3 text-gain" />
                ) : m.trend === 'bearish' ? (
                  <ArrowDown className="h-3 w-3 text-loss" />
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
            <Badge variant="outline" className="text-xs text-warning border-warning/30">
              <AlertTriangle className="h-3 w-3 mr-1" />
              Données insuffisantes
            </Badge>
          )}
        </div>
      )}

      {/* ── Chart ── */}
      <div className="h-72">
        <ResponsiveLine
          data={series}
          theme={theme}
          margin={{ top: 12, right: 16, bottom: 28, left: 72 }}
          xScale={{ type: 'point' }}
          yScale={{ type: 'linear', min: yMin, max: yMax, stacked: false }}
          curve="monotoneX"
          enablePoints={false}
          enableGridX={false}
          axisBottom={{ tickSize: 0, tickPadding: 8, tickValues }}
          axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => formatPrice(v as number) }}
          layers={['grid', 'axes', BandLayer, RefLinesLayer, LinesLayer, 'slices']}
          enableSlices="x"
          sliceTooltip={({ slice }) => (
            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
              <p className="mb-1.5 text-xs text-muted-foreground">{slice.points[0]?.data.x as string}</p>
              {slice.points.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-4">
                  <span className="text-xs text-muted-foreground">
                    {SERIES_LABELS[p.seriesId as string] ?? p.seriesId}
                  </span>
                  <span className="font-mono text-sm tabular-nums">
                    {formatCurrency(p.data.y as number)}
                  </span>
                </div>
              ))}
            </div>
          )}
          animate
          motionConfig="gentle"
        />
      </div>

      {/* Chart legend */}
      {showReality && (
        <div className="flex items-center justify-center gap-4 mt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-[oklch(var(--chart-3))] inline-block rounded" />
            Prix réel
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-[oklch(var(--chart-5))] inline-block rounded" style={{ borderTop: '2px dashed oklch(var(--chart-5))', height: 0 }} />
            Prix prédit
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-[oklch(var(--muted-foreground))] inline-block rounded" />
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
        const explanations = selectedPrediction.explanations!
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
                        className={`h-full rounded-full ${isUp ? 'bg-gain' : 'bg-loss'}`}
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                    <div className="flex items-center gap-1 w-16 justify-end">
                      {isUp ? (
                        <ArrowUp className="h-3 w-3 text-gain" />
                      ) : (
                        <ArrowDown className="h-3 w-3 text-loss" />
                      )}
                      <span className={`text-xs font-medium ${isUp ? 'text-gain' : 'text-loss'}`}>
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

      {/* Regime Info */}
      {selectedPrediction.regime_info && (() => {
        const ri = selectedPrediction.regime_info!
        const regimeClass = REGIME_COLORS[ri.dominant_regime] || REGIME_COLORS.neutral
        return (
          <div className="mt-4 p-4 rounded-lg bg-muted/30 border">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Régime de marché</span>
            </div>

            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Badge className={regimeClass}>
                {REGIME_LABELS[ri.dominant_regime] || ri.dominant_regime}
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
                  Weekly: {REGIME_LABELS[ri.weekly_regime] || ri.weekly_regime}
                </span>
              )}
            </div>

            {ri.probabilities && (
              <div className="space-y-1.5 mb-3">
                {Object.entries(ri.probabilities)
                  .sort(([, a], [, b]) => b - a)
                  .map(([regime, prob]) => (
                    <div key={regime} className="flex items-center gap-2">
                      <span className="text-xs w-16 text-muted-foreground capitalize">{REGIME_LABELS[regime] || regime}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full ${REGIME_BAR_COLORS[regime] || 'bg-gray-400'}`}
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

            {ri.liquidity_warning && (
              <div className="mt-2 flex items-start gap-2 p-2 rounded bg-warning/10 border border-warning/20">
                <Droplets className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                <p className="text-xs text-warning dark:text-warning">{ri.liquidity_warning}</p>
              </div>
            )}
          </div>
        )
      })()}

      {/* Track Record */}
      <TrackRecordPanel symbol={selectedPrediction.symbol} />
    </div>
  )
}
