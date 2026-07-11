import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ResponsivePie } from '@nivo/pie'
import { ResponsiveRadar } from '@nivo/radar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { HelpCircle } from 'lucide-react'
import type { AnalyticsData } from './types'

/**
 * Répartition par classe d'actifs + radar « Profil de risque »
 * (copiés d'AnalyticsPage, pilotés par le sélecteur unique du pilier).
 */

const COLORS = ['oklch(var(--chart-5))', 'oklch(var(--chart-3))', 'oklch(var(--chart-1))', 'oklch(var(--chart-4))', 'oklch(var(--chart-2))', 'oklch(var(--chart-2))', 'oklch(var(--chart-5))', 'oklch(var(--chart-3))']

// Ordre des tokens aligné sur COLORS, pour résoudre des couleurs rgb() compatibles Nivo
const COLOR_TOKENS = ['--chart-5', '--chart-3', '--chart-1', '--chart-4', '--chart-2', '--chart-2', '--chart-5', '--chart-3']

interface AllocationRiskChartsProps {
  analytics: AnalyticsData
  diversificationScore: number
}

export default function AllocationRiskCharts({ analytics, diversificationScore }: AllocationRiskChartsProps) {
  const { theme, color } = useNivoTheme()

  const allocationByTypeData = useMemo(
    () =>
      Object.entries(analytics.allocation_by_type || {}).map(([name, value], index) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: Math.round(value * 10) / 10,
        color: color(COLOR_TOKENS[index % COLOR_TOKENS.length]),
      })),
    [analytics.allocation_by_type, color]
  )

  const riskScoreData = useMemo(
    () => [
      {
        metric: 'Rendement',
        value: Math.min(100, Math.max(0, (analytics.total_gain_loss_percent ?? 0) * 0.5 + 50)),
        fullMark: 100,
      },
      {
        metric: 'Sharpe',
        value: Math.min(100, Math.max(0, (analytics.sharpe_ratio ?? 0) * 25 + 50)),
        fullMark: 100,
      },
      {
        metric: 'Diversification',
        value: diversificationScore,
        fullMark: 100,
      },
      {
        metric: 'Stabilité',
        value: Math.min(100, Math.max(0, 100 - Math.abs(analytics.max_drawdown ?? 0) * 1.25)),
        fullMark: 100,
      },
      {
        metric: 'Sortino',
        value: Math.min(100, Math.max(0, (analytics.sortino_ratio ?? 0) * 25 + 50)),
        fullMark: 100,
      },
    ],
    [
      analytics.total_gain_loss_percent,
      analytics.sharpe_ratio,
      analytics.max_drawdown,
      analytics.sortino_ratio,
      diversificationScore,
    ]
  )

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Répartition par classe d'actifs */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Répartition par classe d'actifs</CardTitle>
        </CardHeader>
        <CardContent>
          {allocationByTypeData.length <= 1 ? (
            <div className="h-64 flex flex-col items-center justify-center text-center">
              <div className="h-24 w-24 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: `${COLORS[0]}20` }}>
                <span className="text-2xl font-serif font-medium" style={{ color: COLORS[0] }}>100%</span>
              </div>
              <p className="text-sm font-medium">{allocationByTypeData[0]?.name || 'N/A'}</p>
              <p className="text-xs text-muted-foreground mt-1">Classe unique — diversifiez pour voir la répartition</p>
            </div>
          ) : (
            <div className="h-64">
              <ResponsivePie
                data={allocationByTypeData.map((d) => ({
                  id: d.name,
                  label: d.name,
                  value: d.value,
                  color: d.color,
                }))}
                theme={theme}
                margin={{ top: 12, right: 12, bottom: 12, left: 12 }}
                innerRadius={0.62}
                padAngle={2}
                cornerRadius={3}
                colors={{ datum: 'data.color' }}
                borderWidth={2}
                borderColor={color('--background')}
                arcLabelsSkipAngle={12}
                arcLabel={(d) => `${d.value}%`}
                arcLabelsTextColor={color('--background')}
                enableArcLinkLabels={false}
                isInteractive
                tooltip={({ datum }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="text-sm font-medium">{datum.label}</p>
                    <p className="mt-0.5 font-mono text-sm tabular-nums">{datum.value}%</p>
                  </div>
                )}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Radar de risque */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Profil de risque
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger aria-label="Aide sur le profil de risque">
                  <HelpCircle className="h-4 w-4 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p className="text-xs">Plus la surface est grande, meilleur est le profil. Rendement, Sharpe et Sortino centrés à 50 (neutre). Stabilité = 100 - |drawdown|.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveRadar
              data={riskScoreData}
              keys={['value']}
              indexBy="metric"
              theme={theme}
              maxValue={100}
              margin={{ top: 28, right: 48, bottom: 28, left: 48 }}
              gridLevels={5}
              gridShape="circular"
              gridLabelOffset={12}
              colors={[color('--chart-4')]}
              fillOpacity={0.2}
              borderWidth={2}
              borderColor={{ from: 'color' }}
              dotSize={6}
              dotColor={color('--chart-4')}
              dotBorderWidth={2}
              dotBorderColor={color('--background')}
              enableDotLabel={false}
              isInteractive
              motionConfig="gentle"
              sliceTooltip={({ index, data }) => (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                  <p className="text-sm font-medium">{index}</p>
                  <p className="mt-0.5 font-mono text-sm tabular-nums text-muted-foreground">
                    {(data[0]?.value as number).toFixed(0)}/100
                  </p>
                </div>
              )}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
