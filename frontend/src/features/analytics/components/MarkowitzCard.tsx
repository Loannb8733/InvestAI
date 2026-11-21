import type { UseMutationResult } from '@tanstack/react-query'
import { Info, ListChecks, Loader2, Shuffle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { OptimizeData, OptimizeObjective, RebalanceResponse } from '../types'
import RebalanceOrders from './RebalanceOrders'

interface MarkowitzCardProps {
  optimization: OptimizeData
  allocationByAsset: Record<string, number>
  objective: OptimizeObjective
  onObjectiveChange: (objective: OptimizeObjective) => void
  rebalance: UseMutationResult<RebalanceResponse, Error, Record<string, number>>
}

function OptimalWeights({ optimization, allocationByAsset }: Pick<MarkowitzCardProps, 'optimization' | 'allocationByAsset'>) {
  const assetCount = Object.keys(optimization.weights).length
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
            Avec seulement {assetCount} actif{assetCount > 1 ? 's' : ''}, l'optimisation concentre tout sur un seul. Ajoutez des actifs diversifiés pour une allocation plus pertinente.
          </p>
        </div>
      )}
      <div className="space-y-2">
        {significantWeights.map(([symbol, weight]) => {
          const diff = weight - (allocationByAsset[symbol] || 0)
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
}

function ExpectedMetrics({ optimization }: { optimization: OptimizeData }) {
  return (
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
  )
}

export default function MarkowitzCard({ optimization, allocationByAsset, objective, onObjectiveChange, rebalance }: MarkowitzCardProps) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <Shuffle className="h-5 w-5 text-accent" />
              Markowitz ({objective === 'max_sharpe' ? 'max Sharpe' : 'volatilité min'})
            </CardTitle>
            <CardDescription>
              {objective === 'max_sharpe' ? 'Portefeuille maximisant le Sharpe ratio' : 'Portefeuille minimisant la volatilité'}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-muted-foreground">Objectif</span>
            <Select value={objective} onValueChange={(v) => onObjectiveChange(v as OptimizeObjective)}>
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
          <OptimalWeights optimization={optimization} allocationByAsset={allocationByAsset} />
          <ExpectedMetrics optimization={optimization} />
          <div className="pt-3 border-t space-y-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={rebalance.isPending}
              onClick={() => rebalance.mutate(optimization.weights)}
            >
              {rebalance.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <ListChecks className="h-4 w-4 mr-2" />}
              Générer les ordres de rééquilibrage
            </Button>
            {rebalance.isError && (
              <p className="text-xs text-loss text-center">
                Impossible de générer les ordres de rééquilibrage. Veuillez réessayer.
              </p>
            )}
            {rebalance.isSuccess && <RebalanceOrders result={rebalance.data} />}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
