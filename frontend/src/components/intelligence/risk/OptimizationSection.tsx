import type { UseMutationResult } from '@tanstack/react-query'
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
import {
  ArrowDownRight,
  ArrowUpRight,
  Info,
  ListChecks,
  Loader2,
  RefreshCw,
  Shield,
  Shuffle,
} from 'lucide-react'
import type {
  OptimizeData,
  OptimizeObjective,
  PlanOrderInput,
  RebalanceResponse,
  RebalancingOrder,
} from './types'

/**
 * Section « Optimisation & rééquilibrage » : les DEUX moteurs côte à côte.
 *
 * - Markowitz (Analytics) : optimise les poids à partir des rendements de la
 *   période d'analyse sélectionnée, avec choix d'objectif (Sharpe max /
 *   volatilité min) et génération d'ordres de rééquilibrage.
 * - MPT Smart Insights : ordres issus du diagnostic de santé, directement
 *   planifiables (pont vers Signaux Alpha).
 */

interface OptimizationSectionProps {
  optimization: OptimizeData | undefined
  allocationByAsset: Record<string, number>
  assetCount: number
  optimizeObjective: OptimizeObjective
  onObjectiveChange: (objective: OptimizeObjective) => void
  rebalanceMutation: UseMutationResult<RebalanceResponse, Error, Record<string, number>>
  mptOrders: RebalancingOrder[]
  plannedSymbols: Set<string>
  onPlanOrder: (order: PlanOrderInput) => void
  isPlanningOrder: boolean
  isBearMode: boolean
  isBullMode: boolean
}

export default function OptimizationSection({
  optimization,
  allocationByAsset,
  assetCount,
  optimizeObjective,
  onObjectiveChange,
  rebalanceMutation,
  mptOrders,
  plannedSymbols,
  onPlanOrder,
  isPlanningOrder,
  isBearMode,
  isBullMode,
}: OptimizationSectionProps) {
  if (!optimization && mptOrders.length === 0) return null

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-serif font-medium">Optimisation &amp; rééquilibrage</h2>
        <p className="text-sm text-muted-foreground">
          Deux moteurs indépendants : Markowitz optimise les poids à partir des rendements de la
          période d'analyse, tandis que le moteur MPT de Smart Insights part du diagnostic de santé
          — fenêtres et contraintes différentes, leurs cibles peuvent donc diverger.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2 items-start">
        {/* ── Moteur 1 : Markowitz (Analytics) ── */}
        {optimization && (
          <Card elevation="raised">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1.5">
                  <CardTitle className="flex items-center gap-2">
                    <Shuffle className="h-5 w-5 text-accent" />
                    Markowitz ({optimizeObjective === 'max_sharpe' ? 'max Sharpe' : 'volatilité min'})
                  </CardTitle>
                  <CardDescription>
                    {optimizeObjective === 'max_sharpe'
                      ? 'Portefeuille maximisant le Sharpe ratio'
                      : 'Portefeuille minimisant la volatilité'}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-muted-foreground">Objectif</span>
                  <Select
                    value={optimizeObjective}
                    onValueChange={(v) => onObjectiveChange(v as OptimizeObjective)}
                  >
                    <SelectTrigger className="h-8 w-36" aria-label="Objectif d'optimisation">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="max_sharpe">Sharpe max</SelectItem>
                      <SelectItem value="min_volatility">Volatilité min</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Poids optimaux */}
                {(() => {
                  const significantWeights = Object.entries(optimization.weights)
                    .sort((a, b) => b[1] - a[1])
                    .filter((entry) => entry[1] >= 0.5)
                  const isSingleAsset = significantWeights.length === 1 && significantWeights[0][1] >= 99
                  return (
                    <>
                      {isSingleAsset && (
                        <div className="flex items-start gap-2 p-3 rounded-md bg-warning/10 border border-warning/30 text-sm">
                          <Info className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                          <p className="text-warning dark:text-warning">
                            Avec seulement {Object.keys(optimization.weights).length} actif{Object.keys(optimization.weights).length > 1 ? 's' : ''}, l'optimisation concentre tout sur un seul. Ajoutez des actifs diversifiés pour une allocation plus pertinente.
                          </p>
                        </div>
                      )}
                      <div className="space-y-2">
                        {significantWeights.map(([symbol, weight]) => {
                          const current = allocationByAsset[symbol] || 0
                          const diff = weight - current
                          return (
                            <div key={symbol} className="flex items-center gap-2">
                              <span className="text-sm font-medium w-16">{symbol}</span>
                              <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                                <div className="h-full bg-accent rounded-full" style={{ width: `${weight}%` }} />
                              </div>
                              <span className="text-xs font-mono w-12 text-right">{weight.toFixed(1)}%</span>
                              <span className={`text-xs font-mono w-16 text-right ${diff > 0 ? 'text-gain' : diff < 0 ? 'text-loss' : 'text-muted-foreground'}`}>
                                {diff > 0 ? '+' : ''}{diff.toFixed(1)}%
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    </>
                  )
                })()}
                {/* Métriques espérées */}
                <div className="grid grid-cols-3 gap-3 pt-2 border-t">
                  <div className="text-center">
                    <div className="text-lg font-bold text-gain">{optimization.expected_return > 0 ? '+' : ''}{optimization.expected_return.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Rendement espéré</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold">{optimization.expected_volatility.toFixed(1)}%</div>
                    <div className="text-xs text-muted-foreground">Volatilité</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-accent">{optimization.sharpe_ratio.toFixed(2)}</div>
                    <div className="text-xs text-muted-foreground">Sharpe optimal</div>
                  </div>
                </div>

                {/* Ordres de rééquilibrage */}
                <div className="pt-3 border-t space-y-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={rebalanceMutation.isPending}
                    onClick={() => rebalanceMutation.mutate(optimization.weights)}
                  >
                    {rebalanceMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <ListChecks className="h-4 w-4 mr-2" />
                    )}
                    Générer les ordres de rééquilibrage
                  </Button>

                  {rebalanceMutation.isError && (
                    <p className="text-xs text-loss text-center">
                      Impossible de générer les ordres de rééquilibrage. Veuillez réessayer.
                    </p>
                  )}

                  {rebalanceMutation.isSuccess && (() => {
                    const actionableOrders = (rebalanceMutation.data?.orders ?? []).filter(
                      (o) => o.action === 'buy' || o.action === 'sell'
                    )
                    if (actionableOrders.length === 0) {
                      return (
                        <p className="text-xs text-muted-foreground text-center py-2">
                          Aucun ordre nécessaire — votre allocation est déjà proche de la cible.
                        </p>
                      )
                    }
                    return (
                      <>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b">
                                <th scope="col" className="text-left p-2 font-medium">Actif</th>
                                <th scope="col" className="text-center p-2 font-medium">Action</th>
                                <th scope="col" className="text-right p-2 font-medium">Montant</th>
                                <th scope="col" className="text-right p-2 font-medium">Poids actuel → cible</th>
                              </tr>
                            </thead>
                            <tbody>
                              {actionableOrders.map((order) => (
                                <tr key={order.symbol} className="border-b last:border-b-0">
                                  <td className="p-2">
                                    <div className="font-medium">{order.symbol}</div>
                                    <div className="text-xs text-muted-foreground">{order.name}</div>
                                  </td>
                                  <td className="p-2 text-center">
                                    <span className={`inline-flex items-center gap-1 text-xs font-medium ${order.action === 'buy' ? 'text-gain' : 'text-loss'}`}>
                                      {order.action === 'buy' ? (
                                        <ArrowUpRight className="h-3 w-3" />
                                      ) : (
                                        <ArrowDownRight className="h-3 w-3" />
                                      )}
                                      {order.action === 'buy' ? 'Acheter' : 'Vendre'}
                                    </span>
                                  </td>
                                  <td className={`p-2 text-right font-mono ${order.action === 'buy' ? 'text-gain' : 'text-loss'}`}>
                                    {order.action === 'buy' ? '+' : '−'}{formatCurrency(Math.abs(order.diff_value))}
                                  </td>
                                  <td className="p-2 text-right font-mono text-xs">
                                    {order.current_weight.toFixed(1)}% → {order.target_weight.toFixed(1)}%
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <p className="text-xs text-muted-foreground text-center">
                          Ordres suggérés (optimisation Markowitz) — ne constitue pas un conseil en investissement.
                        </p>
                      </>
                    )
                  })()}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        {!optimization && assetCount < 2 && (
          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shuffle className="h-5 w-5 text-accent" />
                Markowitz (max Sharpe)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                L'optimisation Markowitz nécessite au moins 2 actifs dans le portefeuille.
              </p>
            </CardContent>
          </Card>
        )}

        {/* ── Moteur 2 : MPT Smart Insights ── */}
        {mptOrders.length > 0 && (
          <Card elevation="raised">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RefreshCw className="h-5 w-5 text-accent" />
                MPT Smart Insights
              </CardTitle>
              <CardDescription>
                Ordres suggérés pour optimiser le ratio de Sharpe (MPT) — planifiables dans Signaux Alpha
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="text-left p-2">Actif</th>
                      <th scope="col" className="text-center p-2">Action</th>
                      <th scope="col" className="text-right p-2">Poids actuel</th>
                      <th scope="col" className="text-right p-2">Poids cible</th>
                      <th scope="col" className="text-right p-2">Montant</th>
                      <th scope="col" className="text-left p-2">Raison</th>
                      <th scope="col" className="text-right p-2">
                        <span className="sr-only">Planifier</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mptOrders.map((order, idx) => (
                      <tr key={idx} className="border-b last:border-b-0">
                        <td className="p-2">
                          <div className="font-medium">{order.symbol}</div>
                          <div className="text-xs text-muted-foreground">{order.name}</div>
                        </td>
                        <td className="p-2 text-center">
                          <Badge variant={order.action === 'buy' ? 'default' : order.action === 'hold' ? 'outline' : 'destructive'}
                            className={order.action === 'hold' ? 'border-warning text-warning dark:text-warning' : ''}>
                            {order.action === 'buy' ? (
                              <ArrowUpRight className="h-3 w-3 mr-1" />
                            ) : order.action === 'hold' ? (
                              <Shield className="h-3 w-3 mr-1" />
                            ) : (
                              <ArrowDownRight className="h-3 w-3 mr-1" />
                            )}
                            {order.action === 'buy' ? (isBearMode ? 'Accumuler' : 'Acheter') : order.action === 'hold' ? 'Conserver' : (isBullMode ? 'Prendre profits' : 'Vendre')}
                          </Badge>
                        </td>
                        <td className="p-2 text-right">{((order.current_weight ?? 0) * 100).toFixed(1)}%</td>
                        <td className="p-2 text-right">{((order.target_weight ?? 0) * 100).toFixed(1)}%</td>
                        <td className="p-2 text-right font-mono">
                          <span className={order.action === 'buy' ? 'text-gain' : order.action === 'hold' ? 'text-warning' : 'text-loss'}>
                            {order.action === 'buy' ? '+' : order.action === 'hold' ? '~' : '-'}{formatCurrency(Math.abs(order.amount_eur ?? 0))}
                          </span>
                        </td>
                        <td className="p-2 text-xs text-muted-foreground max-w-[200px]">{order.reason}</td>
                        <td className="p-2 text-right">
                          {(order.action === 'buy' || order.action === 'sell') && (
                            plannedSymbols.has(order.symbol) ? (
                              <span className="text-xs text-gain">Planifié ✓</span>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs"
                                disabled={isPlanningOrder}
                                onClick={() =>
                                  onPlanOrder({
                                    symbol: order.symbol,
                                    side: order.action as 'buy' | 'sell',
                                    amount_eur: Math.abs(order.amount_eur ?? 0),
                                  })
                                }
                              >
                                Planifier
                              </Button>
                            )
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </section>
  )
}
