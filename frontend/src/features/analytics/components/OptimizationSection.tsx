import type { UseMutationResult } from '@tanstack/react-query'
import { Shuffle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { OptimizeData, OptimizeObjective, PlanOrderInput, RebalanceResponse, RebalancingOrder } from '../types'
import MarkowitzCard from './MarkowitzCard'
import MptOrdersCard, { type MarketMode } from './MptOrdersCard'

interface OptimizationSectionProps {
  optimization: OptimizeData | undefined
  allocationByAsset: Record<string, number>
  assetCount: number
  objective: OptimizeObjective
  onObjectiveChange: (objective: OptimizeObjective) => void
  rebalance: UseMutationResult<RebalanceResponse, Error, Record<string, number>>
  mptOrders: RebalancingOrder[]
  plannedSymbols: Set<string>
  onPlanOrder: (order: PlanOrderInput) => void
  isPlanningOrder: boolean
  mode: MarketMode
}

function MarkowitzUnavailable() {
  return (
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
  )
}

export default function OptimizationSection({
  optimization,
  allocationByAsset,
  assetCount,
  objective,
  onObjectiveChange,
  rebalance,
  mptOrders,
  plannedSymbols,
  onPlanOrder,
  isPlanningOrder,
  mode,
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
        {optimization && (
          <MarkowitzCard
            optimization={optimization}
            allocationByAsset={allocationByAsset}
            objective={objective}
            onObjectiveChange={onObjectiveChange}
            rebalance={rebalance}
          />
        )}
        {!optimization && assetCount < 2 && <MarkowitzUnavailable />}
        {mptOrders.length > 0 && (
          <MptOrdersCard
            orders={mptOrders}
            plannedSymbols={plannedSymbols}
            onPlanOrder={onPlanOrder}
            isPlanningOrder={isPlanningOrder}
            mode={mode}
          />
        )}
      </div>
    </section>
  )
}
