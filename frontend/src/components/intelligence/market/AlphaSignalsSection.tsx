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
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  AlertTriangle,
  Lightbulb,
  Shield,
  ShieldAlert,
  Target,
  Zap,
} from 'lucide-react'

/**
 * Section « Signaux Alpha » du pilier Marché & Signaux.
 *
 * Reprend l'onglet Top Alpha de l'ancienne page Insights : score Alpha +
 * lecture Alpha × Cycle (constats descriptifs, sans recommandation) + simulation
 * Monte Carlo d'un montant choisi par l'utilisateur. Aucun montant n'est proposé
 * et aucun achat n'est « validé » : l'application est ouverte à des tiers et ne
 * rend pas de conseil en investissement personnalisé.
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
                Cet actif représente déjà {top.weight_pct.toFixed(0)}% de votre portefeuille :
                sa variation pèse fortement sur l'ensemble.
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


type Tone = 'favorable' | 'neutre' | 'défavorable'

interface StrategyRow {
  symbol: string
  name: string
  alpha_score: number
  alpha_level: string
  regime: string
  regime_confidence: number
  tone: Tone
  description: string
  value: number
  weight_pct: number
  predicted_7d_pct: number
  is_resilient?: boolean
}

interface StrategyMapData {
  rows: StrategyRow[]
  total_portfolio_value: number
  market_regime: string
  fear_greed: number | null
  summary: { favorable: number; neutral: number; unfavorable: number }
}

interface SimulationResult {
  found?: boolean
  reason?: string
  symbol: string
  score: number
  regime: string
  tone: Tone
  amount_eur: number
  post_purchase_weight_pct: number
  concentration_status: string
  prob_ruin_before: number
  prob_ruin_after: number
  risk_impact: string
  mc_before?: { prob_positive?: number }
  mc_after?: { prob_positive?: number }
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

const toneStyles: Record<Tone, string> = {
  favorable: 'bg-gain/10 text-gain border border-gain/30',
  neutre: 'bg-gray-500/10 text-gray-700 dark:text-gray-300 border border-gray-500/30',
  défavorable: 'bg-loss/10 text-loss border border-loss/30',
}
const toneLabels: Record<Tone, string> = {
  favorable: 'Configuration favorable',
  neutre: 'Configuration neutre',
  défavorable: 'Configuration défavorable',
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

  const [simulationRow, setSimulationRow] = useState<StrategyRow | null>(null)
  const [amountInput, setAmountInput] = useState('')
  const simulationMutation = useMutation<SimulationResult, Error, { symbol: string; amount_eur: number }>({
    mutationFn: predictionsApi.validateSignal,
  })

  const openSimulation = (row: StrategyRow) => {
    setSimulationRow(row)
    setAmountInput('')
    simulationMutation.reset()
  }

  const amount = Number(amountInput.replace(',', '.'))
  const amountValid = amountInput.trim() !== '' && Number.isFinite(amount) && amount > 0

  const runSimulation = (event: React.FormEvent) => {
    event.preventDefault()
    if (!simulationRow || !amountValid) return
    simulationMutation.mutate({ symbol: simulationRow.symbol, amount_eur: amount })
  }

  if (isLoading) return <StrategyTableSkeleton />
  if (!data || data.rows.length === 0) return null

  const plannedSymbols = new Set(
    (plannedOrders || []).filter(o => o.status === 'pending').map(o => o.symbol)
  )

  const result = simulationMutation.data

  return (
    <>
      <Card elevation="raised">
        <CardHeader>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Lecture Alpha × Cycle
              </CardTitle>
              <CardDescription>
                Constat technique pour chaque actif détenu, en croisant le score Alpha et la phase de cycle
              </CardDescription>
            </div>
            <div className="flex items-center gap-2 text-sm flex-wrap">
              {data.summary.favorable > 0 && (
                <Badge className={toneStyles.favorable}>{data.summary.favorable} favorable{data.summary.favorable > 1 ? 's' : ''}</Badge>
              )}
              {data.summary.unfavorable > 0 && (
                <Badge className={toneStyles['défavorable']}>{data.summary.unfavorable} défavorable{data.summary.unfavorable > 1 ? 's' : ''}</Badge>
              )}
              {data.summary.neutral > 0 && (
                <Badge variant="secondary">{data.summary.neutral} neutre{data.summary.neutral > 1 ? 's' : ''}</Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Alpha</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Phase</th>
                  <th scope="col" className="text-left py-2 px-3 text-xs font-medium">Constat</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">
                    <span className="sr-only">Simulation</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.symbol} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-3 px-3">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
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
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                              Ordre planifié
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
                        <span className="text-sm font-bold tabular-nums">{row.alpha_score.toFixed(0)}</span>
                        <span className="text-[10px] text-muted-foreground capitalize">{row.alpha_level}</span>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <Badge variant="outline" className={regimeColors[row.regime] || 'text-gray-500'}>
                        {regimeLabels[row.regime] || row.regime}
                      </Badge>
                    </td>
                    <td className="py-3 px-3 min-w-0">
                      <Badge className={`text-xs ${toneStyles[row.tone] || toneStyles.neutre}`}>
                        {toneLabels[row.tone] || row.tone}
                      </Badge>
                      <p className="text-xs text-muted-foreground mt-1">{row.description}</p>
                    </td>
                    <td className="py-3 px-3 text-right">
                      <Button variant="outline" size="sm" onClick={() => openSimulation(row)}>
                        Simuler
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-start gap-2 p-2 rounded bg-muted/30">
            <Lightbulb className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              Le constat croise le score Alpha (configuration technique à court terme) et la phase du cycle de marché.
              Il décrit une situation : information générale, pas un conseil en investissement. « Simuler » mesure
              l'effet d'un montant que vous choisissez sur le risque du portefeuille.
            </p>
          </div>
        </CardContent>
      </Card>

      <Dialog open={simulationRow !== null} onOpenChange={(open) => { if (!open) setSimulationRow(null) }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Simulation d'un achat hypothétique {simulationRow ? `— ${simulationRow.symbol}` : ''}
            </DialogTitle>
            <DialogDescription>
              Effet d'un montant que vous fixez sur la probabilité de ruine à 90 jours (Monte Carlo) et sur la concentration.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={runSimulation} className="flex items-end gap-2">
            <div className="flex-1 min-w-0">
              <Label htmlFor="simulation-amount">Montant (€)</Label>
              <Input
                id="simulation-amount"
                inputMode="decimal"
                placeholder="Montant de votre choix"
                value={amountInput}
                onChange={(e) => setAmountInput(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={!amountValid || simulationMutation.isPending}>
              Simuler
            </Button>
          </form>

          {simulationMutation.isPending ? (
            <div className="space-y-3 py-2">
              <Skeleton className="h-16 w-full" />
              <div className="grid grid-cols-2 gap-3">
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
              </div>
            </div>
          ) : simulationMutation.isError ? (
            <div className="py-4 text-center">
              <AlertTriangle className="h-8 w-8 mx-auto text-loss mb-2" />
              <p className="text-sm text-muted-foreground">La simulation a échoué. Réessayez dans un instant.</p>
            </div>
          ) : result && result.found === false ? (
            <p className="text-sm text-muted-foreground py-2">{result.reason}</p>
          ) : result ? (
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border text-center">
                  <p className="text-xs text-muted-foreground mb-1">Prob. de ruine actuelle</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{result.prob_ruin_before}%</p>
                  <p className="text-xs text-muted-foreground">P(+): {result.mc_before?.prob_positive?.toFixed(1)}%</p>
                </div>
                <div className="p-3 rounded-lg border text-center">
                  <p className="text-xs text-muted-foreground mb-1">Avec {formatCurrency(result.amount_eur)}</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{result.prob_ruin_after}%</p>
                  <p className="text-xs text-muted-foreground">P(+): {result.mc_after?.prob_positive?.toFixed(1)}%</p>
                </div>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                <span className="text-sm font-medium">Probabilité de ruine</span>
                <Badge variant="outline">{result.risk_impact}</Badge>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span>Poids de {result.symbol} après l'achat simulé</span>
                <span className={`font-mono font-medium ${
                  result.concentration_status === 'ALERTE' ? 'text-loss' :
                  result.concentration_status === 'VIGILANCE' ? 'text-warning' :
                  'text-muted-foreground'
                }`}>
                  {result.post_purchase_weight_pct}% ({result.concentration_status})
                </span>
              </div>

              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Simulation statistique sur l'historique de volatilité, sans valeur prédictive : information générale,
                pas un conseil en investissement.
              </p>
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
