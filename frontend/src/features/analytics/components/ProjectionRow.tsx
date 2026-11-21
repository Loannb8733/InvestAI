import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MonteCarloData, StressTestData } from '../types'
import MonteCarloCard from './MonteCarloCard'
import StressTestCard from './StressTestCard'

interface ProjectionRowProps {
  monteCarlo: MonteCarloData | undefined
  stressTest: StressTestData | undefined
  horizon: string
  onHorizonChange: (horizon: string) => void
}

const HORIZONS = ['30', '90', '180', '365']

export default function ProjectionRow({ monteCarlo, stressTest, horizon, onHorizonChange }: ProjectionRowProps) {
  const simulated = monteCarlo && monteCarlo.simulations > 0 ? monteCarlo : undefined
  const stressed = stressTest && stressTest.scenarios.length > 0 ? stressTest : undefined
  if (!simulated && !stressed) return null

  return (
    <div className="grid gap-4 lg:grid-cols-2 items-start">
      {simulated && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-end gap-2">
            <span className="text-xs text-muted-foreground">Horizon de projection</span>
            <Select value={horizon} onValueChange={onHorizonChange}>
              <SelectTrigger className="h-8 w-28" aria-label="Horizon de projection Monte Carlo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HORIZONS.map((days) => (
                  <SelectItem key={days} value={days}>{`${days} jours`}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1">
            <MonteCarloCard monteCarlo={simulated} />
          </div>
        </div>
      )}
      {stressed && (
        <StressTestCard
          scenarios={stressed.scenarios}
          totalValue={stressed.total_value}
          currency={stressed.currency}
          maxDrawdown={stressed.max_drawdown}
        />
      )}
    </div>
  )
}
