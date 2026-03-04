import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Zap } from 'lucide-react'

interface MonteCarloData {
  percentiles: Record<string, number>
  expected_return: number
  prob_positive: number
  prob_loss_10: number
  prob_ruin: number
  simulations: number
  horizon_days: number
}

interface MonteCarloCardProps {
  monteCarlo: MonteCarloData
}

export default function MonteCarloCard({ monteCarlo }: MonteCarloCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-purple-500" />
          Simulation Monte Carlo
        </CardTitle>
        <CardDescription>
          {monteCarlo.simulations.toLocaleString()} simulations sur {monteCarlo.horizon_days} jours
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Distribution bars */}
          <div className="space-y-2">
            {[
              { label: 'Pessimiste (5%)', value: monteCarlo.percentiles.p5, color: 'bg-red-500' },
              { label: 'Bas (25%)', value: monteCarlo.percentiles.p25, color: 'bg-orange-500' },
              { label: 'Médian (50%)', value: monteCarlo.percentiles.p50, color: 'bg-blue-500' },
              { label: 'Haut (75%)', value: monteCarlo.percentiles.p75, color: 'bg-green-400' },
              { label: 'Optimiste (95%)', value: monteCarlo.percentiles.p95, color: 'bg-green-600' },
            ].map((p) => (
              <div key={p.label} className="flex items-center gap-3">
                <span className="text-xs w-28 text-muted-foreground">{p.label}</span>
                <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden relative">
                  <div
                    className={`h-full ${p.color} rounded-full absolute`}
                    style={{
                      width: `${Math.min(100, Math.max(2, Math.abs(p.value)))}%`,
                      left: p.value < 0 ? `${Math.max(0, 50 + p.value / 2)}%` : '50%',
                    }}
                  />
                  <div className="absolute left-1/2 top-0 bottom-0 w-px bg-foreground/30" />
                </div>
                <span className={`text-xs font-mono w-16 text-right ${p.value >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {p.value > 0 ? '+' : ''}{p.value.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
          {/* Stats */}
          <div className="grid grid-cols-4 gap-3 pt-2 border-t">
            <div className="text-center">
              <div className="text-lg font-bold">{monteCarlo.expected_return > 0 ? '+' : ''}{monteCarlo.expected_return.toFixed(1)}%</div>
              <div className="text-xs text-muted-foreground">Rendement moyen</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-green-500">{monteCarlo.prob_positive.toFixed(0)}%</div>
              <div className="text-xs text-muted-foreground">Prob. gain</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-red-500">{monteCarlo.prob_loss_10.toFixed(0)}%</div>
              <div className="text-xs text-muted-foreground">Prob. perte &gt;10%</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-red-700">{(monteCarlo.prob_ruin ?? 0).toFixed(1)}%</div>
              <div className="text-xs text-muted-foreground">Prob. ruine</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
