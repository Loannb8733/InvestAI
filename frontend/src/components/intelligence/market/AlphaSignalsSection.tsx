import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { formatCurrency } from '@/lib/utils'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import SharedEmptyState from '@/components/ui/empty-state'
import {
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Lightbulb,
  Minus,
  Shield,
  ShieldAlert,
  Target,
  Zap,
} from 'lucide-react'

/**
 * Section « Signaux Alpha » du pilier Marché & Signaux.
 *
 * Reprend l'onglet Top Alpha de l'ancienne page Insights : score Alpha /
 * top opportunités + Matrice de Stratégie (croisement Alpha × Cycle) + modal
 * de validation Monte Carlo avec critères de rejet explicites.
 *
 * Les bandeaux de contexte de régime de la matrice (« Mode Accumulation »,
 * « Mode Prise de Profits »…) ont été supprimés : le régime vit dans
 * RegimeHeader (partagé) et la recommandation de posture dans la carte
 * « Suggestion de posture » de la section Cycle & contexte.
 * Les onglets Frais / Tax-Loss / Revenus passifs / Backtest DCA d'Insights
 * ne font PAS partie de ce pilier (ils migrent vers Rapports).
 */

// ── Top Alpha ────────────────────────────────────────────────────────

interface AlphaReason {
  label: string
  detail: string
  score: number
}

interface AlphaAsset {
  symbol: string
  name: string
  asset_type: string
  current_price: number
  score: number
  predicted_7d_pct: number
  prediction_source?: string
  reasons: AlphaReason[]
  regime: string
  regime_confidence: number
  value: number
  weight_pct: number
}

function TopAlpha() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.predictions.topAlpha,
    queryFn: predictionsApi.getTopAlpha,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <AlphaLoader />
  if (!data || !data.found) {
    return (
      <SharedEmptyState
        icon={Zap}
        title="Aucun actif risqué détecté"
        description="L'analyse Alpha nécessite des positions en cryptomonnaies, actions ou ETF. Les stablecoins et le cash sont exclus."
      />
    )
  }

  const top: AlphaAsset = data.top_alpha
  const allScores: AlphaAsset[] = data.all_scores || []
  const concentrationRisk: boolean = data.concentration_risk

  const scoreColor = top.score >= 80 ? 'text-gain' : top.score >= 50 ? 'text-warning' : 'text-muted-foreground'
  const predColor = top.predicted_7d_pct >= 0 ? 'text-gain' : 'text-loss'

  return (
    <div className="space-y-4">
      {/* Main Alpha Card */}
      <Card elevation="raised">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-warning" />
                Potentiel de Sursaut
              </CardTitle>
              <CardDescription>
                Actif avec la meilleure configuration technique à court terme
              </CardDescription>
            </div>
            <div className="text-right">
              <div className={`text-3xl font-serif font-medium ${scoreColor}`}>{top.score.toFixed(0)}</div>
              <div className="text-xs text-muted-foreground">/100</div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Concentration Risk Warning */}
          {concentrationRisk && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-warning dark:bg-warning/30 border border-warning dark:border-warning">
              <ShieldAlert className="h-4 w-4 text-warning shrink-0" />
              <p className="text-sm text-warning dark:text-warning">
                Cet actif représente déjà {top.weight_pct.toFixed(0)}% de votre portefeuille.
                Prudence avant de renforcer.
              </p>
            </div>
          )}

          {/* Asset Header */}
          <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
            <div>
              <div className="text-lg font-bold">{top.symbol}</div>
              <div className="text-sm text-muted-foreground">{top.name}</div>
              <Badge variant="outline" className="mt-1">{top.asset_type}</Badge>
            </div>
            <div className="text-right">
              <div className="text-sm text-muted-foreground">Prix actuel</div>
              <div className="text-lg font-semibold">{formatCurrency(top.current_price)}</div>
              <div className={`text-sm font-medium ${predColor}`}>
                {top.predicted_7d_pct >= 0 ? '+' : ''}{top.predicted_7d_pct.toFixed(2)}% prédit à 7j
                {top.prediction_source === 'ema20_slope' && (
                  <span className="text-[10px] text-muted-foreground ml-1">(EMA)</span>
                )}
              </div>
            </div>
          </div>

          {/* Reasons */}
          <div>
            <h4 className="text-sm font-semibold mb-2">Raisons techniques</h4>
            <div className="space-y-2">
              {top.reasons.map((reason, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg border">
                  <div>
                    <div className="text-sm font-medium">{reason.label}</div>
                    <div className="text-xs text-muted-foreground">{reason.detail}</div>
                  </div>
                  <Badge variant={reason.score >= 20 ? 'default' : 'secondary'}>
                    +{reason.score}
                  </Badge>
                </div>
              ))}
              {top.reasons.length === 0 && (
                <p className="text-sm text-muted-foreground">Aucun signal technique fort détecté.</p>
              )}
            </div>
          </div>

          {/* Regime Info */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Lightbulb className="h-4 w-4" />
            Régime: <Badge variant="outline">{top.regime}</Badge>
            (confiance {(top.regime_confidence * 100).toFixed(0)}%)
          </div>
        </CardContent>
      </Card>

      {/* Scoreboard — other assets */}
      {allScores.length > 1 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="text-base">Classement Alpha</CardTitle>
            <CardDescription>Tous vos actifs classés par score de surperformance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {allScores.map((asset, i) => (
                <div key={asset.symbol} className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-bold text-muted-foreground w-5">{i + 1}</span>
                    <div>
                      <span className="font-medium">{asset.symbol}</span>
                      <span className="text-xs text-muted-foreground ml-2">{asset.name}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`text-sm ${asset.predicted_7d_pct >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {asset.predicted_7d_pct >= 0 ? '+' : ''}{asset.predicted_7d_pct.toFixed(2)}%
                    </span>
                    <Badge variant={asset.score >= 60 ? 'default' : 'secondary'}>
                      {asset.score.toFixed(0)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Strategy Table — Matrice de décision Alpha × Cycle ───────────────

interface StrategyRow {
  symbol: string
  name: string
  alpha_score: number
  alpha_level: string
  regime: string
  regime_confidence: number
  action: string
  description: string
  value: number
  weight_pct: number
  impact_pct: number
  impact_eur: number
  predicted_7d_pct: number
  is_resilient?: boolean
}

interface StrategyMapData {
  rows: StrategyRow[]
  total_portfolio_value: number
  market_regime: string
  fear_greed: number | null
  summary: { buys: number; sells: number; holds: number }
}

const regimeLabels: Record<string, string> = {
  bullish: 'Mark-up', bearish: 'Markdown', top: 'Topping', bottom: 'Bottoming',
  markup: 'Mark-up', markdown: 'Markdown', topping: 'Topping', bottoming: 'Bottoming',
  accumulation: 'Accumulation', distribution: 'Distribution',
}
const regimeColors: Record<string, string> = {
  bullish: 'bg-gain/10 text-gain border-gain/30',
  bearish: 'bg-loss/10 text-loss border-loss/30',
  top: 'bg-warning/10 text-warning border-warning/30',
  bottom: 'bg-accent/10 text-accent border-accent/30',
  markup: 'bg-gain/10 text-gain border-gain/30',
  markdown: 'bg-loss/10 text-loss border-loss/30',
  topping: 'bg-warning/10 text-warning border-warning/30',
  bottoming: 'bg-accent/10 text-accent border-accent/30',
  accumulation: 'bg-warning/10 text-warning border-warning/30',
  distribution: 'bg-accent/10 text-accent border-accent/30',
}

const actionStyles: Record<string, string> = {
  'ACHAT FORT': 'bg-gain text-white',
  'DCA': 'bg-gain/10 text-gain border border-gain/30',
  'MAINTENIR': 'bg-gray-500/10 text-gray-700 border border-gray-500/30',
  'CONSERVER': 'bg-gray-500/10 text-gray-700 border border-gray-500/30',
  'OBSERVER': 'bg-accent/10 text-accent border border-accent/30',
  'ATTENDRE': 'bg-warning/10 text-warning border border-warning/30',
  'ÉVITER': 'bg-warning/10 text-warning border border-warning/30',
  'PRENDRE PROFITS': 'bg-warning/10 text-warning border border-warning/30',
  'ALLÉGER': 'bg-warning/10 text-warning border border-warning/30',
  'VENDRE': 'bg-loss text-white',
  'PLANIFIER': 'bg-accent/10 text-accent border border-accent/30',
}

interface PlannedOrder {
  id: string
  symbol: string
  action: string
  order_eur: number
  source: string
  status: string
  created_at: string | null
}

function StrategyTable() {
  const { data, isLoading } = useQuery<StrategyMapData>({
    queryKey: queryKeys.predictions.strategyMap,
    queryFn: predictionsApi.getStrategyMap,
    staleTime: 5 * 60 * 1000,
  })

  const { data: plannedOrders } = useQuery<PlannedOrder[]>({
    queryKey: queryKeys.predictions.plannedOrders,
    queryFn: predictionsApi.getPlannedOrders,
    staleTime: 30 * 1000,
  })

  const [signalModalOpen, setSignalModalOpen] = useState(false)
  const validateSignalMutation = useMutation({
    mutationFn: predictionsApi.validateSignal,
  })

  const handleActionClick = (row: StrategyRow) => {
    setSignalModalOpen(true)
    validateSignalMutation.mutate({ symbol: row.symbol, action: row.action })
  }

  if (isLoading) return <StrategyTableSkeleton />
  if (!data || data.rows.length === 0) return null

  // Set of symbols with pending planned orders
  const plannedSymbols = new Set(
    (plannedOrders || []).filter(o => o.status === 'pending').map(o => o.symbol)
  )

  const totalImpact = data.rows.reduce((sum, r) => sum + r.impact_eur, 0)
  const signal = validateSignalMutation.data

  return (
    <>
      <Card elevation="raised">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Matrice de Stratégie
              </CardTitle>
              <CardDescription>
                Croisement Alpha × Cycle pour chaque actif — actions recommandées
              </CardDescription>
            </div>
            <div className="flex items-center gap-3 text-sm">
              {data.summary.buys > 0 && (
                <Badge className="bg-gain/10 text-gain border border-gain/30">
                  {data.summary.buys} Achat{data.summary.buys > 1 ? 's' : ''}
                </Badge>
              )}
              {data.summary.sells > 0 && (
                <Badge className="bg-loss/10 text-loss border border-loss/30">
                  {data.summary.sells} Vente{data.summary.sells > 1 ? 's' : ''}
                </Badge>
              )}
              {data.summary.holds > 0 && (
                <Badge variant="secondary">
                  {data.summary.holds} Maintien{data.summary.holds > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* NOTE : les bandeaux de contexte de régime (Mode Accumulation /
              Expansion / Prise de Profits) qui vivaient ici sont supprimés —
              le régime est affiché par RegimeHeader et la posture par la
              carte « Suggestion de posture » (section Cycle & contexte). */}

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Alpha</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Phase</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Action</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">Impact Portefeuille</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => {
                  const impactSign = row.impact_eur > 0 ? '+' : row.impact_eur < 0 ? '-' : ''
                  const isActionable = ['ACHAT FORT', 'DCA', 'VENDRE', 'ALLÉGER', 'PRENDRE PROFITS'].includes(row.action)

                  return (
                    <tr key={row.symbol} className={`border-b last:border-0 hover:bg-muted/50 ${plannedSymbols.has(row.symbol) ? 'bg-primary/5' : ''}`}>
                      <td className="py-3 px-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{row.symbol}</span>
                            {row.name !== row.symbol && (
                              <span className="text-xs text-muted-foreground">{row.name}</span>
                            )}
                            {row.is_resilient && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-warning/50 text-warning gap-0.5">
                                <Shield className="h-3 w-3" />
                                Bouclier
                              </Badge>
                            )}
                            {plannedSymbols.has(row.symbol) && (
                              <Badge className="bg-primary text-primary-foreground text-[10px] px-1.5 py-0">
                                À EXÉCUTER
                              </Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {formatCurrency(row.value)} · {row.weight_pct}%
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex flex-col items-center gap-0.5">
                          <span className={`text-sm font-bold ${
                            row.alpha_score >= 60 ? 'text-gain' :
                            row.alpha_score >= 30 ? 'text-warning' : 'text-muted-foreground'
                          }`}>
                            {row.alpha_score.toFixed(0)}
                          </span>
                          <span className="text-[10px] text-muted-foreground capitalize">{row.alpha_level}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant="outline" className={regimeColors[row.regime] || 'text-gray-500'}>
                          {regimeLabels[row.regime] || row.regime}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-center">
                        {isActionable ? (
                          <Badge
                            className={`text-xs cursor-pointer hover:opacity-80 transition-opacity ${actionStyles[row.action] || 'bg-gray-100 text-gray-700'}`}
                            onClick={() => handleActionClick(row)}
                          >
                            {row.action}
                          </Badge>
                        ) : (
                          <Badge className={`text-xs ${actionStyles[row.action] || 'bg-gray-100 text-gray-700'}`}>
                            {row.action}
                          </Badge>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {row.impact_eur > 0 ? (
                            <ArrowUpRight className="h-3 w-3 text-gain" />
                          ) : row.impact_eur < 0 ? (
                            <ArrowDownRight className="h-3 w-3 text-loss" />
                          ) : (
                            <Minus className="h-3 w-3 text-muted-foreground" />
                          )}
                          <span className={`text-sm font-medium tabular-nums ${
                            row.impact_eur > 0 ? 'text-gain' :
                            row.impact_eur < 0 ? 'text-loss' : 'text-muted-foreground'
                          }`}>
                            {impactSign}{formatCurrency(Math.abs(row.impact_eur))}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            ({row.impact_pct > 0 ? '+' : ''}{row.impact_pct}%)
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr className="border-t">
                  <td colSpan={4} className="py-3 px-3 text-sm font-medium text-right">
                    Impact total estimé
                  </td>
                  <td className="py-3 px-3 text-right">
                    <span className={`text-sm font-bold tabular-nums ${
                      totalImpact > 0 ? 'text-gain' :
                      totalImpact < 0 ? 'text-loss' : 'text-muted-foreground'
                    }`}>
                      {totalImpact > 0 ? '+' : ''}{formatCurrency(totalImpact)}
                    </span>
                    <span className="text-xs text-muted-foreground ml-1">
                      sur {formatCurrency(data.total_portfolio_value)}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-start gap-2 p-2 rounded bg-muted/30">
            <Lightbulb className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              L'action est déterminée par le croisement du score Alpha (potentiel technique) et de la phase du cycle de marché.
              Cliquez sur un badge actionnable pour valider le signal avec Monte Carlo.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Signal Validation Modal */}
      <Dialog open={signalModalOpen} onOpenChange={setSignalModalOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Validation du Signal
            </DialogTitle>
            <DialogDescription>
              Simulation Monte Carlo de l'impact sur la probabilité de ruine
            </DialogDescription>
          </DialogHeader>

          {validateSignalMutation.isPending ? (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </div>
              <Skeleton className="h-24 w-full" />
              <div className="grid grid-cols-2 gap-3">
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
              </div>
            </div>
          ) : validateSignalMutation.isError ? (
            <div className="py-6 text-center">
              <AlertTriangle className="h-8 w-8 mx-auto text-loss mb-2" />
              <p className="text-sm text-muted-foreground">Erreur lors de la validation du signal</p>
            </div>
          ) : signal ? (
            <div className="space-y-4 py-2">
              {/* Asset & Action */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div>
                  <div className="font-bold text-lg">{signal.symbol}</div>
                  <div className="text-sm text-muted-foreground">
                    Score: {signal.score}/100 · {signal.regime}
                  </div>
                </div>
                <div className="text-right">
                  <Badge className={actionStyles[signal.action] || 'bg-gray-100 text-gray-700'}>
                    {signal.action}
                  </Badge>
                  <div className="text-sm font-mono mt-1">{formatCurrency(signal.order_eur)}</div>
                </div>
              </div>

              {/* Monte Carlo comparison */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border text-center">
                  <p className="text-xs text-muted-foreground mb-1">Prob. de ruine AVANT</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{signal.prob_ruin_before}%</p>
                  <p className="text-xs text-muted-foreground">
                    P(+): {signal.mc_before?.prob_positive?.toFixed(1)}%
                  </p>
                </div>
                <div className={`p-3 rounded-lg border text-center ${
                  signal.prob_ruin_after <= signal.prob_ruin_before
                    ? 'border-gain/30 bg-gain/5'
                    : 'border-loss/30 bg-loss/5'
                }`}>
                  <p className="text-xs text-muted-foreground mb-1">Prob. de ruine APRÈS</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{signal.prob_ruin_after}%</p>
                  <p className="text-xs text-muted-foreground">
                    P(+): {signal.mc_after?.prob_positive?.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* Risk impact */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                <span className="text-sm font-medium">Impact risque</span>
                <Badge variant="outline" className={
                  signal.risk_impact === 'Diminuée' ? 'border-gain text-gain' :
                  signal.risk_impact === 'Augmentée' ? 'border-loss text-loss' :
                  'border-gray-500 text-gray-600'
                }>
                  {signal.risk_impact}
                </Badge>
              </div>

              {/* Concentration */}
              <div className="flex items-center justify-between text-sm">
                <span>Concentration post-achat</span>
                <span className={`font-mono font-medium ${
                  signal.concentration_status === 'ALERTE' ? 'text-loss' :
                  signal.concentration_status === 'VIGILANCE' ? 'text-warning' :
                  'text-gain'
                }`}>
                  {signal.post_purchase_weight_pct}% ({signal.concentration_status})
                </span>
              </div>

              {/* Verdict */}
              <div className={`p-3 rounded-lg text-center ${
                signal.validated
                  ? 'bg-gain/10 border border-gain/30'
                  : 'bg-loss/10 border border-loss/30'
              }`}>
                <p className={`font-bold ${signal.validated ? 'text-gain' : 'text-loss'}`}>
                  {signal.validated ? 'Signal validé' : 'Signal rejeté'}
                </p>
                {!signal.validated && signal.reason && (
                  <p className="text-xs text-muted-foreground mt-1">{signal.reason}</p>
                )}
                {/* Critères explicites : un rejet sans explication du seuil
                    (score > 85 exigé côté backend) était incompréhensible. */}
                {!signal.validated && !signal.reason && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {signal.score <= 85 && `Score ${signal.score}/100 ≤ 85 (seuil de validation). `}
                    {signal.impact_pct <= 0 && 'Impact prédit non positif. '}
                    {signal.weight_overflow && 'Poids post-achat au-delà de la limite de concentration.'}
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  )
}

// ── Skeletons ────────────────────────────────────────────────────────

function AlphaLoader() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-72 mt-1" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
        <div className="flex gap-3 mt-4">
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
        </div>
      </CardContent>
    </Card>
  )
}

function StrategyTableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-44" />
        <Skeleton className="h-4 w-80 mt-1" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-6 w-12" />
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-4 w-24 ml-auto" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Section principale ───────────────────────────────────────────────

export default function AlphaSignalsSection() {
  return (
    <div className="space-y-4">
      <TopAlpha />
      <StrategyTable />
    </div>
  )
}
