import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { formatCurrency } from '@/lib/utils'
import type { PortfolioPrediction, WhatIfResult } from '@/types/predictions'
import { Loader2, Target } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const STABLECOINS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'USDP', 'FDUSD', 'PYUSD']

const SCENARIOS = [
  { label: 'Crash', value: -50, color: 'bg-red-500/10 text-red-500 hover:bg-red-500/20' },
  { label: 'Bear', value: -30, color: 'bg-red-500/10 text-red-400 hover:bg-red-500/20' },
  { label: 'Correction', value: -15, color: 'bg-orange-500/10 text-orange-500 hover:bg-orange-500/20' },
  { label: 'Rebond', value: 20, color: 'bg-green-500/10 text-green-500 hover:bg-green-500/20' },
  { label: 'Bull', value: 50, color: 'bg-green-500/10 text-green-400 hover:bg-green-500/20' },
  { label: 'Moon', value: 100, color: 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20' },
]

interface PredictionSimulationTabProps {
  predictions: PortfolioPrediction[]
  whatIfSymbol: string
  setWhatIfSymbol: (v: string) => void
  whatIfChange: number
  setWhatIfChange: (v: number) => void
  whatIfResult: WhatIfResult | null
  whatIfLoading: boolean
  runWhatIf: () => void
}

export default function PredictionSimulationTab({
  predictions,
  whatIfSymbol,
  setWhatIfSymbol,
  whatIfChange,
  setWhatIfChange,
  whatIfResult,
  whatIfLoading,
  runWhatIf,
}: PredictionSimulationTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5 text-blue-500" />
          Scénario What-If
        </CardTitle>
        <CardDescription>Simulez l'impact d'une variation de prix sur votre portefeuille</CardDescription>
      </CardHeader>
      <CardContent>
        {predictions.length > 0 ? (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-2 block">Actif</label>
                <Select value={whatIfSymbol} onValueChange={setWhatIfSymbol}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {predictions.map(p => (
                      <SelectItem key={p.symbol} value={p.symbol}>
                        {p.symbol}{p.name && p.name !== p.symbol ? ` - ${p.name}` : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-sm font-medium mb-2 block">
                  Variation: <span className={`font-bold ${whatIfChange >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {whatIfChange >= 0 ? '+' : ''}{whatIfChange}%
                  </span>
                </label>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {SCENARIOS.map((scenario) => (
                    <button
                      key={scenario.value}
                      onClick={() => {
                        setWhatIfChange(scenario.value)
                        setTimeout(runWhatIf, 50)
                      }}
                      className={`text-xs px-2.5 py-1 rounded-full border cursor-pointer transition-colors ${scenario.color} ${whatIfChange === scenario.value ? 'ring-1 ring-primary' : ''}`}
                    >
                      {scenario.label} ({scenario.value > 0 ? '+' : ''}{scenario.value}%)
                    </button>
                  ))}
                </div>
                <input
                  type="range"
                  min="-50"
                  max="100"
                  value={whatIfChange}
                  onChange={(e) => setWhatIfChange(parseInt(e.target.value))}
                  onMouseUp={runWhatIf}
                  onTouchEnd={runWhatIf}
                  className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>-50%</span>
                  <span>0%</span>
                  <span>+100%</span>
                </div>
              </div>

              {whatIfLoading && <Loader2 className="h-5 w-5 animate-spin text-primary" />}

              {whatIfResult && (
                <div className="space-y-3 pt-2">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground">Valeur actuelle</p>
                      <p className="text-lg font-bold">{formatCurrency(whatIfResult.current_value)}</p>
                    </div>
                    <div className={`p-3 rounded-lg ${whatIfResult.impact_percent >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                      <p className="text-xs text-muted-foreground">Valeur simulée</p>
                      <p className={`text-lg font-bold ${whatIfResult.impact_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {formatCurrency(whatIfResult.simulated_value)}
                      </p>
                    </div>
                  </div>
                  <p className={`text-center font-bold text-lg ${whatIfResult.impact_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {whatIfResult.impact_percent >= 0 ? '+' : ''}{whatIfResult.impact_percent.toFixed(2)}% sur le portefeuille
                  </p>
                </div>
              )}
            </div>

            {whatIfResult && whatIfResult.per_asset.length > 0 && (() => {
              const filteredAssets = whatIfResult.per_asset.filter(
                a => !STABLECOINS.includes(a.symbol.toUpperCase()) || Math.abs(a.impact) > 0.01
              )
              return filteredAssets.length > 0 ? (
                <div>
                  <p className="text-sm font-medium mb-2">Impact par actif</p>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={filteredAssets.map(a => ({ name: a.symbol, impact: a.impact }))}
                        layout="vertical"
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" tickFormatter={(v) => formatCurrency(v).replace('€', '')} />
                        <YAxis type="category" dataKey="name" width={50} tick={{ fontSize: 12 }} />
                        <RechartsTooltip formatter={(value: number) => formatCurrency(value)} />
                        <Bar dataKey="impact" radius={4}>
                          {filteredAssets.map((a, i) => (
                            <Cell key={i} fill={a.impact >= 0 ? '#10b981' : '#ef4444'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ) : null
            })()}
          </div>
        ) : (
          <p className="text-center text-muted-foreground py-8">Aucun actif disponible</p>
        )}
      </CardContent>
    </Card>
  )
}
