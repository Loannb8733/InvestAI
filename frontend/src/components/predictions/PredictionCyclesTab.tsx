import React from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { CycleGauge } from './PredictionMetricCard'
import type { MarketCycleData } from '@/types/predictions'
import {
  AlertTriangle,
  Brain,
  Loader2,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  Target,
  Activity,
  BarChart3,
  Layers,
  Repeat,
  Clock,
  Flame,
} from 'lucide-react'

// ── Shared maps ──────────────────────────────────────────────────────

const REGIME_LABEL: Record<string, string> = {
  bullish: 'Haussier', bearish: 'Baissier', top: 'Sommet', bottom: 'Creux', neutral: 'Neutre',
}
const REGIME_BADGE: Record<string, string> = {
  bullish: 'bg-green-500/10 text-green-500',
  bearish: 'bg-red-500/10 text-red-500',
  top: 'bg-amber-500/10 text-amber-500',
  bottom: 'bg-blue-500/10 text-blue-500',
  neutral: 'bg-gray-500/10 text-gray-500',
}
const BAR_COLOR: Record<string, string> = {
  bullish: 'bg-green-500', bearish: 'bg-red-500', top: 'bg-amber-500', bottom: 'bg-blue-500',
}
const TEXT_COLOR: Record<string, string> = {
  bullish: 'text-green-500', bearish: 'text-red-500', top: 'text-amber-500', bottom: 'text-blue-500', neutral: 'text-gray-500',
}

// ── Top / Bottom Card ────────────────────────────────────────────────

const TopBottomCard = React.memo(({ estimates }: { estimates: MarketCycleData['top_bottom_estimates'] }) => {
  if (!estimates) return null
  const { btc, per_asset } = estimates
  const allEstimates = btc ? [btc, ...per_asset.filter(a => a.symbol !== 'BTC')] : per_asset
  if (allEstimates.length === 0) return null

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
                        {isBtc && <Badge variant="outline" className="text-[10px] px-1.5 py-0">Réf.</Badge>}
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                          est.current_regime === 'bearish' ? 'text-red-500 border-red-500/30' :
                          est.current_regime === 'bullish' ? 'text-green-500 border-green-500/30' :
                          est.current_regime === 'top' ? 'text-amber-500 border-amber-500/30' :
                          est.current_regime === 'bottom' ? 'text-blue-500 border-blue-500/30' :
                          'text-gray-500'
                        }`}>
                          {REGIME_LABEL[est.current_regime] || est.current_regime}
                        </Badge>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className="text-sm font-medium tabular-nums">{formatCurrency(est.current_price)}</span>
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="text-sm font-bold text-blue-500 tabular-nums">{formatCurrency(est.next_bottom.estimated_price)}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground">{formatDate(est.next_bottom.estimated_date)} (~{est.next_bottom.estimated_days}j)</span>
                          <span className="text-[10px] font-medium text-blue-500">-{est.next_bottom.distance_pct.toFixed(1)}%</span>
                        </div>
                        <div className="w-20 h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                          <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, est.next_bottom.distance_pct * 3)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex flex-col items-center gap-0.5">
                        <span className="text-sm font-bold text-amber-500 tabular-nums">{formatCurrency(est.next_top.estimated_price)}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground">{formatDate(est.next_top.estimated_date)} (~{est.next_top.estimated_days}j)</span>
                          <span className="text-[10px] font-medium text-amber-500">+{est.next_top.distance_pct.toFixed(1)}%</span>
                        </div>
                        <div className="w-20 h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                          <div className="h-full rounded-full bg-amber-500" style={{ width: `${Math.min(100, est.next_top.distance_pct * 3)}%` }} />
                        </div>
                      </div>
                    </td>
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
})
TopBottomCard.displayName = 'TopBottomCard'

// ── Probability bars helper ──────────────────────────────────────────

function ProbabilityBars({ probabilities }: { probabilities: Record<string, number> }) {
  return (
    <div className="space-y-1.5">
      {Object.entries(probabilities)
        .sort(([, a], [, b]) => b - a)
        .map(([phase, prob]) => (
          <div key={phase} className="flex items-center gap-2">
            <span className="text-xs w-14 text-muted-foreground capitalize">
              {REGIME_LABEL[phase] || phase}
            </span>
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full ${BAR_COLOR[phase] || 'bg-gray-400'}`} style={{ width: `${(prob * 100).toFixed(1)}%` }} />
            </div>
            <span className="text-xs text-muted-foreground w-10 text-right">{(prob * 100).toFixed(1)}%</span>
          </div>
        ))}
    </div>
  )
}

// ── Main Cycles Tab ──────────────────────────────────────────────────

interface PredictionCyclesTabProps {
  marketCycle: MarketCycleData | undefined
  loadingCycle: boolean
}

export default function PredictionCyclesTab({ marketCycle, loadingCycle }: PredictionCyclesTabProps) {
  if (loadingCycle) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  if (!marketCycle) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-muted-foreground">Impossible de charger l'analyse de cycle</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
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
            <CycleGauge position={marketCycle.cycle_position} />
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
                  <Badge className={REGIME_BADGE[marketCycle.market_regime.dominant_regime] || REGIME_BADGE.neutral}>
                    {REGIME_LABEL[marketCycle.market_regime.dominant_regime] || marketCycle.market_regime.dominant_regime}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    Confiance: {(marketCycle.market_regime.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <ProbabilityBars probabilities={marketCycle.market_regime.probabilities} />
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
                  <Badge className={REGIME_BADGE[marketCycle.portfolio_regime.dominant_regime] || REGIME_BADGE.neutral}>
                    {REGIME_LABEL[marketCycle.portfolio_regime.dominant_regime] || marketCycle.portfolio_regime.dominant_regime}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {marketCycle.per_asset.length} actif{marketCycle.per_asset.length > 1 ? 's' : ''} analysé{marketCycle.per_asset.length > 1 ? 's' : ''}
                  </span>
                </div>
                <ProbabilityBars probabilities={marketCycle.portfolio_regime.probabilities} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">Données indisponibles</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Time-to-Pivot + Distribution Diagnostic */}
      <div className="grid gap-4 lg:grid-cols-2">
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
                    {[marketCycle.time_to_pivot.current_phase, marketCycle.time_to_pivot.next_phase].map((phase, i) => (
                      <React.Fragment key={phase}>
                        {i === 1 && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
                        <Badge variant="outline" className={
                          phase === 'Euphorie' ? 'text-red-500 border-red-500/30' :
                          phase === 'Distribution' ? 'text-amber-500 border-amber-500/30' :
                          phase === 'Expansion' ? 'text-green-500 border-green-500/30' :
                          phase === 'Accumulation' ? 'text-cyan-500 border-cyan-500/30' :
                          'text-blue-500 border-blue-500/30'
                        }>
                          {phase}
                        </Badge>
                      </React.Fragment>
                    ))}
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

                return (
                  <div key={sig.name} className={`p-3 rounded-lg border ${sigColor}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium truncate">{sig.name}</span>
                      <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${TEXT_COLOR[sig.signal] || TEXT_COLOR.neutral}`}>
                        {REGIME_LABEL[sig.signal] || sig.signal}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full ${BAR_COLOR[sig.signal] || 'bg-gray-400'}`}
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

      {/* Per-asset regime */}
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
                        <Badge className={REGIME_BADGE[asset.dominant_regime] || REGIME_BADGE.neutral} variant="outline">
                          {REGIME_LABEL[asset.dominant_regime] || asset.dominant_regime}
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
                                className={BAR_COLOR[phase] || 'bg-gray-400'}
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

      {/* Advice */}
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
    </div>
  )
}
