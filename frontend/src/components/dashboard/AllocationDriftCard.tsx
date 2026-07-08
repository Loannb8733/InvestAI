import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Crosshair, ArrowRight, Target } from 'lucide-react'
import { reportsApi, type RebalancingDrift } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { formatCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'

/**
 * Écart vs allocation cible — le widget de pilotage du dashboard.
 *
 * Transforme le dashboard d'un rétroviseur en instrument d'action : pour
 * chaque classe crypto, position actuelle vs cible persistée, écart coloré
 * par sévérité (≥5 pts = attention, ≥10 pts = agir), et lien direct vers le
 * rééquilibrage (ordres + coût fiscal). Sans cible définie : invitation à en
 * créer une.
 */

const DRIFT_WARN = 5 // points d'écart → attention
const DRIFT_ALERT = 10 // points d'écart → agir

export default function AllocationDriftCard() {
  const { data, isLoading } = useQuery<RebalancingDrift>({
    queryKey: queryKeys.reports.rebalancingDrift,
    queryFn: reportsApi.getRebalancingDrift,
    staleTime: 5 * 60_000,
    meta: { suppressGlobalError: true },
  })

  if (isLoading) {
    return (
      <Card elevation="raised">
        <CardHeader className="pb-2">
          <Skeleton className="h-4 w-44" />
        </CardHeader>
        <CardContent className="space-y-3" aria-hidden>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  // Pas encore de cible : proposer d'en définir une (état vide actionnable)
  if (!data?.targets) {
    return (
      <Card elevation="raised">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Target className="h-4 w-4" aria-hidden />
            Allocation cible
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted-foreground">
            Définis une allocation cible par classe (L1, DeFi, Stablecoins…) pour
            suivre tes écarts et savoir quoi rééquilibrer.
          </p>
          <Button asChild size="sm" variant="outline">
            <Link to="/reports?tab=strategy">
              Définir mon allocation cible
              <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden />
            </Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  const maxDrift = data.max_drift_pct
  const severity = maxDrift >= DRIFT_ALERT ? 'alert' : maxDrift >= DRIFT_WARN ? 'warn' : 'ok'
  // Classes avec une position ou une cible (masque les 0/0)
  const rows = data.categories.filter((c) => c.current_pct > 0 || c.target_pct > 0)

  return (
    <Card elevation="raised">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Crosshair className="h-4 w-4" aria-hidden />
            Écart vs allocation cible
          </CardTitle>
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-xs font-medium tabular',
              severity === 'alert' && 'bg-loss/10 text-loss',
              severity === 'warn' && 'bg-warning/10 text-warning',
              severity === 'ok' && 'bg-gain/10 text-gain'
            )}
            aria-label={`Écart maximal ${maxDrift.toFixed(1)} points`}
          >
            max {maxDrift.toFixed(1)} pts
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {rows.map((c) => {
          const drift = c.drift_pct
          const abs = Math.abs(drift)
          const tone =
            abs >= DRIFT_ALERT ? 'text-loss' : abs >= DRIFT_WARN ? 'text-warning' : 'text-muted-foreground'
          return (
            <div key={c.category}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-medium">{c.label}</span>
                <span className="tabular">
                  {c.current_pct.toFixed(1)} % / cible {c.target_pct.toFixed(1)} %{' '}
                  <span className={cn('font-semibold', tone)}>
                    ({drift >= 0 ? '+' : ''}
                    {drift.toFixed(1)} pt)
                  </span>
                </span>
              </div>
              {/* Barre : position actuelle + repère de cible */}
              <div
                className="relative mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${c.label} : ${c.current_pct.toFixed(1)} % du portefeuille, cible ${c.target_pct.toFixed(1)} %`}
              >
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    abs >= DRIFT_ALERT ? 'bg-loss' : abs >= DRIFT_WARN ? 'bg-warning' : 'bg-primary'
                  )}
                  style={{ width: `${Math.min(100, c.current_pct)}%` }}
                />
                <div
                  aria-hidden
                  className="absolute top-[-2px] h-[10px] w-0.5 rounded bg-foreground/70"
                  style={{ left: `${Math.min(100, c.target_pct)}%` }}
                />
              </div>
            </div>
          )
        })}
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-muted-foreground">
            Poche crypto : {formatCurrency(data.total_crypto_value)}
          </span>
          <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
            <Link to="/reports?tab=strategy">
              Rééquilibrer
              <ArrowRight className="ml-1 h-3 w-3" aria-hidden />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
