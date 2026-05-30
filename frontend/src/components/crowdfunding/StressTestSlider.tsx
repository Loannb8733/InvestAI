import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Loader2, TrendingDown, ShieldAlert, Activity, ArrowRight } from 'lucide-react'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import type { StressTestResult } from '@/types/crowdfunding'

const DELAY_STEPS = [0, 6, 12, 24]
const DELAY_LABELS: Record<number, string> = {
  0: 'Nominal',
  6: '+6 mois',
  12: '+12 mois',
  24: '+24 mois',
}

function getIrrColor(irr: number | null | undefined): string {
  if (irr == null) return 'text-muted-foreground'
  if (irr >= 6) return 'text-gain'
  if (irr >= 3) return 'text-warning'
  return 'text-loss'
}

function getIrrBg(irr: number | null | undefined): string {
  if (irr == null) return 'bg-muted/20'
  if (irr >= 6) return 'bg-gain/10'
  if (irr >= 3) return 'bg-warning/10'
  return 'bg-loss/10'
}

function getGlowRing(irr: number | null | undefined): string {
  if (irr == null) return 'ring-border/50'
  if (irr >= 6) return 'ring-gain/20'
  if (irr >= 3) return 'ring-warning/20'
  return 'ring-loss/20'
}

function getSliderAccent(irr: number | null | undefined): string {
  if (irr == null) return ''
  if (irr >= 6) return '[&_[role=slider]]:bg-gain [&_[role=slider]]:border-gain'
  if (irr >= 3) return '[&_[role=slider]]:bg-warning [&_[role=slider]]:border-warning'
  return '[&_[role=slider]]:bg-loss [&_[role=slider]]:border-loss'
}

interface StressTestSliderProps {
  projectId: string
}

export default function StressTestSlider({ projectId }: StressTestSliderProps) {
  const [sliderIndex, setSliderIndex] = useState(0)
  const delayMonths = DELAY_STEPS[sliderIndex]

  const { data, isLoading, isError } = useQuery<StressTestResult>({
    queryKey: queryKeys.crowdfunding.stressTest(projectId, delayMonths),
    queryFn: () => crowdfundingApi.getStressTest(projectId, delayMonths),
    staleTime: 60_000,
  })

  const displayIrr = (delayMonths === 0 ? data?.base_irr : data?.stressed_irr) ?? null

  return (
    <div className="space-y-5">
      {/* IRR Hero display */}
      <div className={`relative rounded-lg ${getIrrBg(displayIrr)} ring-1 ${getGlowRing(displayIrr)} p-6 text-center transition-all duration-500`}>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2">
          TRI {delayMonths > 0 ? 'dégradé' : 'contractuel'}
        </p>

        {isLoading ? (
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-muted-foreground my-2" />
        ) : isError ? (
          <p className="text-sm text-destructive py-2">Calcul impossible</p>
        ) : (
          <div className="space-y-2">
            <p className={`text-4xl font-serif font-medium tabular-nums transition-all duration-500 ${getIrrColor(displayIrr)}`}>
              {displayIrr !== null && displayIrr !== undefined
                ? `${displayIrr.toFixed(2)}%`
                : '—'}
            </p>
            {data?.irr_delta != null && delayMonths > 0 && (
              <Badge
                variant="outline"
                className="text-loss border-loss/20 bg-loss/5 text-xs"
              >
                <TrendingDown className="h-3 w-3 mr-1" />
                {data.irr_delta.toFixed(2)} pts
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Slider section */}
      <div className="space-y-3 px-1">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="h-3 w-3" />
            Retard simulé
          </span>
          <span className="font-medium text-foreground">{DELAY_LABELS[delayMonths]}</span>
        </div>
        <Slider
          value={[sliderIndex]}
          onValueChange={([v]) => setSliderIndex(v)}
          min={0}
          max={DELAY_STEPS.length - 1}
          step={1}
          className={`w-full ${getSliderAccent(displayIrr)}`}
        />
        <div className="flex justify-between">
          {DELAY_STEPS.map((d, i) => (
            <button
              key={d}
              onClick={() => setSliderIndex(i)}
              className={`text-[11px] tabular-nums px-1.5 py-0.5 rounded transition-all ${
                i === sliderIndex
                  ? 'text-foreground font-medium bg-muted/50'
                  : 'text-muted-foreground hover:text-foreground/70'
              }`}
            >
              {DELAY_LABELS[d]}
            </button>
          ))}
        </div>
      </div>

      {/* Base vs Stressed comparison */}
      {data && delayMonths > 0 && (
        <div className="flex items-center gap-3 rounded-xl bg-muted/20 border border-border/50 p-3">
          <div className="flex-1 text-center">
            <p className="text-[11px] text-muted-foreground mb-1">Contractuel</p>
            <p className={`text-lg font-bold tabular-nums ${getIrrColor(data.base_irr)}`}>
              {data.base_irr != null ? `${data.base_irr.toFixed(2)}%` : '—'}
            </p>
          </div>
          <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
          <div className="flex-1 text-center">
            <p className="text-[11px] text-muted-foreground mb-1 flex items-center justify-center gap-1">
              <Activity className="h-3 w-3" />
              Stressé
            </p>
            <p className={`text-lg font-bold tabular-nums ${getIrrColor(data.stressed_irr)}`}>
              {data.stressed_irr != null ? `${data.stressed_irr.toFixed(2)}%` : '—'}
            </p>
          </div>
        </div>
      )}

      {/* Cashflow mini-info */}
      {data && data.cashflows.length > 0 && (
        <div className="text-[11px] text-muted-foreground flex items-center justify-between px-1">
          <span>{data.cashflows.length} échéance{data.cashflows.length > 1 ? 's' : ''}</span>
          {delayMonths > 0 && (
            <span>
              Fin décalée au{' '}
              {new Date(data.cashflows[data.cashflows.length - 1].date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
