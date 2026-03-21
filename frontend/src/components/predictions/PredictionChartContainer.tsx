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
import {
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
  Line,
  ComposedChart,
} from 'recharts'

// ── Regime labels/colors (shared) ────────────────────────────────────

const REGIME_LABELS: Record<string, string> = {
  bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux', neutral: 'Neutre',
}
const REGIME_COLORS: Record<string, string> = {
  bullish: 'text-green-500 bg-green-500/10',
  bearish: 'text-red-500 bg-red-500/10',
  top: 'text-amber-500 bg-amber-500/10',
  bottom: 'text-blue-500 bg-blue-500/10',
  neutral: 'text-gray-500 bg-gray-500/10',
}
const REGIME_BAR_COLORS: Record<string, string> = {
  bullish: 'bg-green-500', bearish: 'bg-red-500', top: 'bg-amber-500', bottom: 'bg-blue-500',
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

      {/* ── Chart ── */}
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

      {/* Chart legend */}
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
  )
}
