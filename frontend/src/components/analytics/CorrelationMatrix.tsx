import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { HelpCircle } from 'lucide-react'
import { type DisplayThresholds, DEFAULT_DISPLAY_THRESHOLDS } from '@/types'

interface Correlation {
  symbols: string[]
  matrix: number[][]
  strongly_correlated: [string, string, number][]
  negatively_correlated: [string, string, number][]
}

interface CorrelationMatrixProps {
  correlation: Correlation
  days?: number
  thresholds?: DisplayThresholds['correlation']
}

// Build color for correlation value: blue (negative) -> gray (0) -> red (positive)
const corrColor = (v: number, isDiag: boolean) => {
  if (isDiag) return 'bg-muted'
  const abs = Math.abs(v)
  if (v > 0.01) return `rgba(239, 68, 68, ${Math.min(abs * 0.85, 0.85)})`   // red
  if (v < -0.01) return `rgba(59, 130, 246, ${Math.min(abs * 0.85, 0.85)})`  // blue
  return 'rgba(148, 163, 184, 0.1)'
}

const corrTextColor = (v: number) => {
  const abs = Math.abs(v)
  if (abs > 0.55) return 'text-white'
  return ''
}

const corrLabel = (v: number, ct: DisplayThresholds['correlation']) => {
  if (v >= ct.strong_positive) return 'Forte +'
  if (v >= ct.moderate_positive) return 'Modérée +'
  if (v <= ct.strong_negative) return 'Inverse'
  if (v <= ct.moderate_negative) return 'Faible -'
  return ''
}

export default function CorrelationMatrix({ correlation, days, thresholds }: CorrelationMatrixProps) {
  const ct = thresholds ?? DEFAULT_DISPLAY_THRESHOLDS.correlation
  if (correlation.symbols.length <= 1) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Matrice de corrélation
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger aria-label="Aide sur la matrice de corrélation">
                <HelpCircle className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <p className="text-xs">+1 = parfaitement corrélés, 0 = indépendants, -1 = inversement corrélés. Basé sur {days || 60}j de rendements journaliers.</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CardTitle>
        <CardDescription>Comment vos actifs évoluent ensemble</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Heatmap grid */}
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b">
                <th className="p-2 bg-muted/50 sticky left-0 z-10"></th>
                {correlation.symbols.map((sym) => (
                  <th key={sym} className="p-2 text-center font-semibold text-xs bg-muted/50 min-w-[52px]">
                    {sym}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {correlation.symbols.map((sym1, i) => (
                <tr key={sym1} className="border-b last:border-b-0">
                  <td className="p-2 font-semibold text-xs bg-muted/50 sticky left-0 z-10">{sym1}</td>
                  {correlation.symbols.map((sym2, j) => {
                    const value = correlation.matrix[i]?.[j] ?? 0
                    const isDiag = i === j
                    return (
                      <TooltipProvider key={`${sym1}-${sym2}`}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <td
                              className={`p-0 text-center transition-opacity hover:opacity-80 ${isDiag ? 'bg-muted' : ''}`}
                              style={!isDiag ? { backgroundColor: corrColor(value, false) } : undefined}
                            >
                              <div className={`py-2 px-1 text-xs font-mono font-medium ${corrTextColor(value)} ${isDiag ? 'text-muted-foreground' : ''}`}>
                                {isDiag ? '\u2014' : value.toFixed(2)}
                              </div>
                            </td>
                          </TooltipTrigger>
                          {!isDiag && (
                            <TooltipContent>
                              <p className="text-xs font-medium">{sym1} / {sym2}</p>
                              <p className="text-xs text-muted-foreground">
                                Corrélation: {value.toFixed(3)}
                                {corrLabel(value, ct) && ` (${corrLabel(value, ct)})`}
                              </p>
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </TooltipProvider>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Color scale legend */}
        <div className="flex items-center justify-center gap-2">
          <span className="text-xs text-muted-foreground">-1</span>
          <div className="flex h-3 w-48 rounded-full overflow-hidden">
            <div className="flex-1" style={{ background: 'rgba(59, 130, 246, 0.85)' }} />
            <div className="flex-1" style={{ background: 'rgba(59, 130, 246, 0.45)' }} />
            <div className="flex-1" style={{ background: 'rgba(148, 163, 184, 0.2)' }} />
            <div className="flex-1" style={{ background: 'rgba(239, 68, 68, 0.45)' }} />
            <div className="flex-1" style={{ background: 'rgba(239, 68, 68, 0.85)' }} />
          </div>
          <span className="text-xs text-muted-foreground">+1</span>
        </div>

        {/* Notable pairs */}
        {(correlation.strongly_correlated.length > 0 || correlation.negatively_correlated.length > 0) && (
          <div className="grid gap-3 sm:grid-cols-2">
            {correlation.strongly_correlated.length > 0 && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <p className="text-xs font-semibold text-red-500 mb-2">Fortement corrélés (risque de concentration)</p>
                <div className="space-y-1.5">
                  {correlation.strongly_correlated.slice(0, 4).map(([s1, s2, v]) => (
                    <div key={`${s1}-${s2}`} className="flex items-center justify-between">
                      <span className="text-xs">{s1} \u2014 {s2}</span>
                      <span className="text-xs font-mono font-semibold text-red-500">{typeof v === 'number' ? v.toFixed(2) : v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {correlation.negatively_correlated.length > 0 && (
              <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                <p className="text-xs font-semibold text-blue-500 mb-2">Corrélation inverse (bonne diversification)</p>
                <div className="space-y-1.5">
                  {correlation.negatively_correlated.slice(0, 4).map(([s1, s2, v]) => (
                    <div key={`${s1}-${s2}`} className="flex items-center justify-between">
                      <span className="text-xs">{s1} \u2014 {s2}</span>
                      <span className="text-xs font-mono font-semibold text-blue-500">{typeof v === 'number' ? v.toFixed(2) : v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
