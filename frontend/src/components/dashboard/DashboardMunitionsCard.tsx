import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { dashboardApi } from '@/services/api'
import { Zap, AlertTriangle, CheckCircle2, Info, ArrowRight } from 'lucide-react'

interface MunitionsData {
  available_liquidity: number
  total_value: number
  liquidity_pct: number
  invested_pct: number
  next_signal_symbol: string | null
  next_signal_action: string | null
  next_signal_amount: number
  can_execute: boolean
  shortfall: number
  message: string | null
  profile: string
  deploy_to_risk: number
  keep_in_reserve: number
}

const profileLabel: Record<string, string> = {
  aggressive: 'Agressif',
  moderate: 'Modéré',
  conservative: 'Conservateur',
}

export default function DashboardMunitionsCard({ availableLiquidity, totalValue }: { availableLiquidity?: number; totalValue?: number }) {
  const { data, isLoading } = useQuery<MunitionsData>({
    queryKey: ['dashboard', 'munitions'],
    queryFn: () => dashboardApi.getMunitions(),
    staleTime: 60_000,
    retry: 1,
  })

  // Use props as fallback when API hasn't loaded yet
  const liquidity = data?.available_liquidity ?? availableLiquidity ?? 0
  const total = data?.total_value ?? totalValue ?? 0

  if (isLoading && !data && !availableLiquidity) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-400" />
            Munitions Disponibles
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-20 animate-pulse bg-muted rounded" />
        </CardContent>
      </Card>
    )
  }

  const available_liquidity = liquidity
  const total_value = total
  const liquidity_pct = data?.liquidity_pct ?? (total > 0 ? Math.round(liquidity / total * 1000) / 10 : 0)
  const invested_pct = data?.invested_pct ?? (100 - liquidity_pct)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-400" />
            Munitions Disponibles
            <TooltipProvider delayDuration={100}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="h-3 w-3 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p className="text-sm">Cash + Stablecoins disponibles. Prêt à investir en crypto ou crowdfunding.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </span>
          {data?.profile && (
            <Badge variant="outline" className="text-[10px]">
              {profileLabel[data.profile] || data.profile}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Big amount */}
        <div className="text-2xl font-bold text-amber-400">
          {formatCurrency(available_liquidity)}
        </div>

        {/* Progress bar: Invested vs Munitions */}
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>Investi ({invested_pct}%)</span>
            <span>Munitions ({liquidity_pct}%)</span>
          </div>
          <div className="h-2.5 bg-muted rounded-full overflow-hidden flex">
            <div
              className="h-full bg-primary transition-all duration-500"
              style={{ width: `${invested_pct}%` }}
            />
            <div
              className="h-full bg-amber-400 transition-all duration-500"
              style={{ width: `${liquidity_pct}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{formatCurrency(total_value - available_liquidity)}</span>
            <span>{formatCurrency(available_liquidity)}</span>
          </div>
        </div>

        {/* Next Alpha signal */}
        {data?.next_signal_symbol && (
          <div className={`flex items-start gap-2 text-xs rounded-lg p-2.5 ${
            data.can_execute
              ? 'bg-emerald-500/10 border border-emerald-500/20'
              : 'bg-red-500/10 border border-red-500/20'
          }`}>
            {data.can_execute ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-red-400 mt-0.5 shrink-0" />
            )}
            <div className="space-y-0.5">
              <div className={data.can_execute ? 'text-emerald-300' : 'text-red-300'}>
                {data.can_execute
                  ? `Signal ${data.next_signal_action} sur ${data.next_signal_symbol} exécutable`
                  : data.message
                }
              </div>
              {data.next_signal_amount > 0 && (
                <div className="text-muted-foreground">
                  Montant : {formatCurrency(data.next_signal_amount)}
                  {!data.can_execute && ` · Manque ${formatCurrency(data.shortfall)}`}
                </div>
              )}
            </div>
          </div>
        )}

        {/* DCA deployment split */}
        {data && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
            <ArrowRight className="h-3 w-3" />
            <span>
              DCA 300€/mois : {formatCurrency(data.deploy_to_risk)} vers actifs risqués,{' '}
              {formatCurrency(data.keep_in_reserve)} en réserve
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
