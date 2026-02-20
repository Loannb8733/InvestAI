import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import { AlertTriangle } from 'lucide-react'

interface StressScenario {
  name: string
  description: string
  stressed_value: number
  total_loss: number
  total_loss_pct: number
  per_asset: Array<{
    symbol: string
    current_value: number
    stressed_value: number
    loss: number
    shock_pct: number
  }>
}

interface StressTestCardProps {
  scenarios: StressScenario[]
}

export default function StressTestCard({ scenarios }: StressTestCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-orange-500" />
          Stress Tests
        </CardTitle>
        <CardDescription>
          Impact de scénarios de crise historiques sur votre portefeuille
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {scenarios.map((scenario) => (
            <div key={scenario.name} className="rounded-lg border p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{scenario.name}</span>
                <span className="text-sm font-bold text-red-500">
                  {scenario.total_loss_pct.toFixed(1)}%
                </span>
              </div>
              <p className="text-xs text-muted-foreground mb-2">{scenario.description}</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-500 rounded-full"
                    style={{ width: `${Math.min(100, Math.abs(scenario.total_loss_pct))}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-red-500 w-24 text-right">
                  {formatCurrency(scenario.total_loss)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
