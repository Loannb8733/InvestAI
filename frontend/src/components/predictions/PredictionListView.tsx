import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { DisplayThresholds } from '@/types'
import type { PortfolioPrediction, BacktestData, ChartPoint } from '@/types/predictions'
import { ReliabilityScore, VariationBar } from './PredictionMetricCard'
import PredictionChartContainer from './PredictionChartContainer'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Minus,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

// ── Helpers ──────────────────────────────────────────────────────────

function getTrendIcon(trend: string) {
  switch (trend?.toLowerCase()) {
    case 'bullish': return <TrendingUp className="h-4 w-4 text-green-500" />
    case 'bearish': return <TrendingDown className="h-4 w-4 text-red-500" />
    default: return <Minus className="h-4 w-4 text-yellow-500" />
  }
}

function getSignalBadge(trend: string) {
  if (trend === 'bullish') return { variant: 'default' as const, label: 'Haussier' }
  if (trend === 'bearish') return { variant: 'destructive' as const, label: 'Baissier' }
  return { variant: 'secondary' as const, label: 'Neutre' }
}

// ── Component ────────────────────────────────────────────────────────

interface PredictionListViewProps {
  predictions: PortfolioPrediction[]
  selectedAsset: string | null
  setSelectedAsset: (v: string | null) => void
  selectedPrediction?: PortfolioPrediction
  chartData: ChartPoint[]
  showSupportResistance: boolean
  showReality: boolean
  setShowReality: (v: boolean) => void
  loadingBacktest: boolean
  backtestData?: BacktestData
  daysAhead: number
  dt: DisplayThresholds
  formatPrice: (v: number) => string
}

export default function PredictionListView({
  predictions,
  selectedAsset,
  setSelectedAsset,
  selectedPrediction,
  chartData,
  showSupportResistance,
  showReality,
  setShowReality,
  loadingBacktest,
  backtestData,
  daysAhead,
  dt,
  formatPrice,
}: PredictionListViewProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Projections par actif</CardTitle>
        <CardDescription>Cliquez sur un actif pour voir la projection visuelle</CardDescription>
      </CardHeader>
      <CardContent>
        {predictions.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">Actif</th>
                    <th className="text-left py-3 px-4 font-medium">Variation</th>
                    <th className="text-center py-3 px-4 font-medium">Signal</th>
                    <th className="text-center py-3 px-4 font-medium">Fiabilité</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {predictions.map((pred) => {
                    const signal = getSignalBadge(pred.trend)
                    const isSelected = selectedAsset === pred.symbol
                    return (
                      <tr
                        key={pred.symbol}
                        className={`border-b cursor-pointer transition-colors ${isSelected ? 'bg-primary/5' : 'hover:bg-muted/50'}`}
                        onClick={() => setSelectedAsset(isSelected ? null : pred.symbol)}
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div>
                              <p className="font-medium">{pred.symbol}</p>
                              {pred.name && pred.name !== pred.symbol && (
                                <p className="text-xs text-muted-foreground">{pred.name}</p>
                              )}
                            </div>
                            {pred.model_used === 'random_walk' && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    <p className="text-xs">Données historiques insuffisantes — prédiction dégradée</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <VariationBar percent={pred.change_percent} />
                        </td>
                        <td className="text-center py-3 px-4">
                          <div className="flex items-center justify-center gap-2">
                            {getTrendIcon(pred.trend)}
                            <Badge variant={signal.variant} className="text-xs">{signal.label}</Badge>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex justify-center">
                            <ReliabilityScore
                              reliabilityScore={pred.reliability_score}
                              skillScore={pred.skill_score}
                              hitRate={pred.hit_rate}
                              hitRateSignificant={pred.hit_rate_significant}
                              hitRateN={pred.hit_rate_n_samples}
                              modelConfidence={pred.model_confidence}
                            />
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          {isSelected ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Expanded asset detail */}
            {selectedPrediction && chartData.length > 0 && (
              <PredictionChartContainer
                selectedPrediction={selectedPrediction}
                chartData={chartData}
                showSupportResistance={showSupportResistance}
                showReality={showReality}
                setShowReality={setShowReality}
                loadingBacktest={loadingBacktest}
                backtestData={backtestData}
                daysAhead={daysAhead}
                dt={dt}
                formatPrice={formatPrice}
              />
            )}
          </>
        ) : (
          <p className="text-center text-muted-foreground py-8">Aucune prédiction disponible</p>
        )}
      </CardContent>
    </Card>
  )
}
