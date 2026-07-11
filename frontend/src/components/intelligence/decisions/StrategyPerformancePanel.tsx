import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCurrency } from '@/lib/utils'
import { strategiesApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { AlertTriangle, BarChart3 } from 'lucide-react'

interface PerfLine {
  action_id: string
  symbol: string
  action: string
  direction: 'buy' | 'sell'
  amount_eur: number
  executed_at: string
  price_at_execution: number
  price_at_execution_date: string
  current_price: number
  current_price_date: string
  pnl_eur: number
  pnl_pct: number
  baseline_eur: number
}

interface NonEvaluable {
  action_id: string
  symbol: string | null
  action: string
  reason: string
}

interface StrategyPerformanceData {
  strategy_id: string
  strategy_name: string
  strategy_status: string
  lines: PerfLine[]
  non_evaluable: NonEvaluable[]
  total_impact_eur: number
  baseline_no_action_eur: number
  vs_baseline_eur: number
  executed_count: number
  skipped_count: number
  pending_count: number
  non_evaluable_count: number
  follow_rate_pct: number | null
  evaluated_count: number
  sell_note: string
}

function pnlColor(v: number) {
  return v > 0 ? 'text-gain' : v < 0 ? 'text-loss' : 'text-muted-foreground'
}

function signed(v: number) {
  return `${v > 0 ? '+' : ''}${formatCurrency(v)}`
}

/**
 * Performance mesurée d'une stratégie : ce que les actions EXÉCUTÉES ont
 * réellement donné (P&L pour les achats, impact évité/manqué pour les ventes).
 */
export default function StrategyPerformancePanel({ strategyId }: { strategyId: string }) {
  const { data, isLoading, isError } = useQuery<StrategyPerformanceData>({
    queryKey: [...queryKeys.strategies.all, 'performance', strategyId],
    queryFn: () => strategiesApi.getPerformance(strategyId),
    staleTime: 5 * 60 * 1000,
    meta: { suppressGlobalError: true },
  })

  if (isLoading) {
    return (
      <div className="mt-4 pt-4 border-t space-y-2">
        <Skeleton className="h-4 w-40" />
        <div className="grid grid-cols-3 gap-3">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="mt-4 pt-4 border-t flex items-center gap-2 text-xs text-muted-foreground">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        Performance indisponible pour cette stratégie.
      </div>
    )
  }

  return (
    <div className="mt-4 pt-4 border-t space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
        <BarChart3 className="h-3.5 w-3.5" />
        Performance (P&amp;L)
      </p>

      {/* Résumé */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        <div className="p-2.5 rounded-md bg-muted/30">
          <p className="text-[10px] text-muted-foreground uppercase">Impact total</p>
          <p className={`text-sm font-bold tabular-nums ${pnlColor(data.total_impact_eur)}`}>
            {signed(data.total_impact_eur)}
          </p>
        </div>
        <div className="p-2.5 rounded-md bg-muted/30">
          <p className="text-[10px] text-muted-foreground uppercase">vs ne rien faire</p>
          <p className={`text-sm font-bold tabular-nums ${pnlColor(data.vs_baseline_eur)}`}>
            {signed(data.vs_baseline_eur)}
          </p>
        </div>
        <div className="p-2.5 rounded-md bg-muted/30">
          <p className="text-[10px] text-muted-foreground uppercase">Taux de suivi</p>
          <p className="text-sm font-bold tabular-nums">
            {data.follow_rate_pct != null ? `${data.follow_rate_pct}%` : '—'}
          </p>
        </div>
        <div className="p-2.5 rounded-md bg-muted/30">
          <p className="text-[10px] text-muted-foreground uppercase">Actions</p>
          <p className="text-sm font-bold tabular-nums">
            {data.executed_count} exéc. · {data.skipped_count} ign. · {data.pending_count} att.
          </p>
        </div>
      </div>

      {/* Détail par action exécutée */}
      {data.lines.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-left p-2 text-xs font-medium">Actif</th>
                <th scope="col" className="text-center p-2 text-xs font-medium">Action</th>
                <th scope="col" className="text-right p-2 text-xs font-medium">Montant</th>
                <th scope="col" className="text-right p-2 text-xs font-medium">Prix exéc. → actuel</th>
                <th scope="col" className="text-right p-2 text-xs font-medium">P&amp;L / Impact</th>
              </tr>
            </thead>
            <tbody>
              {data.lines.map((line) => (
                <tr key={line.action_id} className="border-b last:border-b-0">
                  <td className="p-2">
                    <span className="font-medium">{line.symbol}</span>
                    <span className="text-[10px] text-muted-foreground ml-1.5">
                      {new Date(line.executed_at).toLocaleDateString('fr-FR')}
                    </span>
                  </td>
                  <td className="p-2 text-center">
                    <Badge
                      variant="outline"
                      className={`text-xs ${line.direction === 'buy' ? 'border-gain/30 text-gain' : 'border-loss/30 text-loss'}`}
                    >
                      {line.action}
                    </Badge>
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">{formatCurrency(line.amount_eur)}</td>
                  <td className="p-2 text-right font-mono tabular-nums text-xs text-muted-foreground">
                    {formatCurrency(line.price_at_execution)} → {formatCurrency(line.current_price)}
                  </td>
                  <td className={`p-2 text-right font-mono tabular-nums font-medium ${pnlColor(line.pnl_eur)}`}>
                    {signed(line.pnl_eur)}
                    <span className="text-[10px] font-normal text-muted-foreground ml-1">
                      ({line.pnl_pct > 0 ? '+' : ''}{line.pnl_pct.toFixed(2)}%)
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.lines.length === 0 && data.non_evaluable.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Aucune action exécutée pour l'instant — la performance sera mesurée dès la première exécution.
        </p>
      )}

      {/* Actions non évaluables */}
      {data.non_evaluable.length > 0 && (
        <div className="space-y-1">
          {data.non_evaluable.map((ne) => (
            <p key={ne.action_id} className="text-[11px] text-muted-foreground flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              {ne.symbol ? `${ne.symbol} — ` : ''}{ne.action} : {ne.reason}
            </p>
          ))}
        </div>
      )}

      {/* Note ventes */}
      {data.lines.some((l) => l.direction === 'sell') && data.sell_note && (
        <p className="text-[10px] text-muted-foreground leading-relaxed">{data.sell_note}</p>
      )}
    </div>
  )
}
