import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import { AlertTriangle, ChevronDown, ChevronUp, Clock, TrendingDown, TrendingUp, Shield } from 'lucide-react'

interface StressScenario {
  id: string
  name: string
  description: string
  duration_days: number
  stressed_value: number
  total_loss: number
  total_loss_pct: number
  estimated_recovery_months: number
  per_asset: Array<{
    symbol: string
    name: string
    current_value: number
    stressed_value: number
    loss: number
    shock_pct: number
    risk_weight: number
  }>
}

interface MaxDrawdown {
  value: number
  scenario: string
  estimated_recovery_months: number
}

interface StressTestCardProps {
  scenarios: StressScenario[]
  totalValue: number
  currency: string
  maxDrawdown: MaxDrawdown | null
}

export default function StressTestCard({ scenarios, totalValue, currency, maxDrawdown }: StressTestCardProps) {
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [showAssets, setShowAssets] = useState(false)

  const active = selectedScenario
    ? scenarios.find((s) => s.id === selectedScenario)
    : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-orange-500" />
          Stress Tests Historiques
        </CardTitle>
        <CardDescription>
          Impact de crises réelles sur votre portefeuille — pondéré par la volatilité de chaque actif
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* MaxDD Banner */}
        {maxDrawdown && (
          <div className="flex items-center gap-3 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 p-3">
            <Shield className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">Drawdown Maximum Théorique</div>
              <div className="text-xs text-muted-foreground">
                Pire scénario : {maxDrawdown.scenario}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-lg font-bold text-red-500">-{maxDrawdown.value.toFixed(1)}%</div>
              {maxDrawdown.estimated_recovery_months > 0 && (
                <div className="text-xs text-muted-foreground flex items-center gap-1 justify-end">
                  <Clock className="h-3 w-3" />
                  ~{maxDrawdown.estimated_recovery_months} mois
                </div>
              )}
            </div>
          </div>
        )}

        {/* Scenario selector grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {scenarios.map((scenario) => {
            const isSelected = selectedScenario === scenario.id
            const isBullish = scenario.total_loss_pct > 0
            return (
              <button
                key={scenario.id}
                onClick={() => setSelectedScenario(isSelected ? null : scenario.id)}
                className={`rounded-lg border p-2.5 text-left transition-all ${
                  isSelected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'hover:bg-muted/50'
                }`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  {isBullish ? (
                    <TrendingUp className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                  )}
                  <span className="text-xs font-medium truncate">{scenario.name}</span>
                </div>
                <div className={`text-sm font-bold ${isBullish ? 'text-green-500' : 'text-red-500'}`}>
                  {scenario.total_loss_pct > 0 ? '+' : ''}{scenario.total_loss_pct.toFixed(1)}%
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {formatCurrency(scenario.total_loss, currency)}
                </div>
              </button>
            )
          })}
        </div>

        {/* Compact list (when no scenario selected) */}
        {!active && (
          <div className="space-y-2">
            {scenarios.map((scenario) => {
              const isBullish = scenario.total_loss_pct > 0
              return (
                <div key={scenario.id} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{scenario.name}</span>
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-bold ${isBullish ? 'text-green-500' : 'text-red-500'}`}>
                        {scenario.total_loss_pct > 0 ? '+' : ''}{scenario.total_loss_pct.toFixed(1)}%
                      </span>
                      {scenario.estimated_recovery_months > 0 && (
                        <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                          <Clock className="h-3 w-3" />
                          {scenario.estimated_recovery_months}m
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mb-2">{scenario.description}</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isBullish ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.min(100, Math.abs(scenario.total_loss_pct))}%` }}
                      />
                    </div>
                    <span className={`text-xs font-mono w-24 text-right ${isBullish ? 'text-green-500' : 'text-red-500'}`}>
                      {formatCurrency(scenario.total_loss, currency)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Detailed comparison view (when scenario selected) */}
        {active && (
          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h4 className="font-medium">{active.name}</h4>
                <p className="text-xs text-muted-foreground mt-0.5">{active.description}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                  <span>Durée : {active.duration_days}j</span>
                  {active.estimated_recovery_months > 0 && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Récupération : ~{active.estimated_recovery_months} mois
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Before / After comparison */}
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-muted/50 p-2">
                <div className="text-xs text-muted-foreground">Actuel</div>
                <div className="text-sm font-bold">{formatCurrency(totalValue, currency)}</div>
              </div>
              <div className="flex items-center justify-center">
                <div className={`text-lg font-bold ${active.total_loss_pct > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  →
                </div>
              </div>
              <div className={`rounded-lg p-2 ${active.total_loss_pct > 0 ? 'bg-green-50 dark:bg-green-950/20' : 'bg-red-50 dark:bg-red-950/20'}`}>
                <div className="text-xs text-muted-foreground">Après scénario</div>
                <div className={`text-sm font-bold ${active.total_loss_pct > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {formatCurrency(active.stressed_value, currency)}
                </div>
              </div>
            </div>

            {/* Per-asset breakdown toggle */}
            <button
              onClick={() => setShowAssets(!showAssets)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showAssets ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              Détail par actif ({active.per_asset.length})
            </button>

            {showAssets && (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {active.per_asset.map((asset) => (
                  <div key={asset.symbol} className="flex items-center justify-between text-xs py-1 border-b border-dashed last:border-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium">{asset.symbol}</span>
                      <span className="text-muted-foreground truncate">{asset.name}</span>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <span className="text-muted-foreground">{formatCurrency(asset.current_value, currency)}</span>
                      <span className={`font-mono font-medium ${asset.shock_pct > 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {asset.shock_pct > 0 ? '+' : ''}{asset.shock_pct.toFixed(1)}%
                      </span>
                      <span className={`font-mono w-20 text-right ${asset.loss > 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {formatCurrency(asset.loss, currency)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
