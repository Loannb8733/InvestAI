import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { ResponsiveBar } from '@nivo/bar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { AnalyticsData } from './types'

/**
 * Barres « Performance par actif » (top 10) + « Top 10 positions »
 * (copiées d'AnalyticsPage, pilotées par le sélecteur unique du pilier).
 */

interface PerformanceChartsProps {
  analytics: AnalyticsData
}

export default function PerformanceCharts({ analytics }: PerformanceChartsProps) {
  const { theme, color } = useNivoTheme()

  const performanceData = useMemo(
    () =>
      [...(analytics.assets || [])]
        .sort((a, b) => b.gain_loss_percent - a.gain_loss_percent)
        .slice(0, 10)
        .map((asset) => ({
          name: asset.symbol,
          performance: Math.round(asset.gain_loss_percent * 10) / 10,
          fill: asset.gain_loss_percent >= 0 ? color('--chart-3') : color('--chart-4'),
        })),
    [analytics.assets, color]
  )

  const allocationByAssetData = useMemo(
    () =>
      Object.entries(analytics.allocation_by_asset || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([name, value]) => ({
          name,
          value: Math.round(value * 10) / 10,
        })),
    [analytics.allocation_by_asset]
  )

  return (
    <>
      {/* Performance par actif */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Performance par actif</CardTitle>
          <CardDescription>Gains/pertes en pourcentage (top 10)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveBar
              data={performanceData}
              keys={['performance']}
              indexBy="name"
              layout="horizontal"
              theme={theme}
              margin={{ top: 8, right: 24, bottom: 32, left: 64 }}
              padding={0.3}
              colors={({ data }) => data.fill}
              borderRadius={4}
              enableLabel={false}
              enableGridX
              enableGridY={false}
              axisBottom={{ tickSize: 0, tickPadding: 8, format: (v) => `${v}%` }}
              axisLeft={{ tickSize: 0, tickPadding: 8 }}
              valueScale={{ type: 'linear' }}
              tooltip={({ indexValue, value, color: barColor }) => (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: barColor }} />
                    <span className="text-xs text-muted-foreground">{indexValue}</span>
                  </span>
                  <p className="mt-0.5 font-mono text-sm tabular-nums">{value}%</p>
                </div>
              )}
              animate
              motionConfig="gentle"
            />
          </div>
        </CardContent>
      </Card>

      {/* Top 10 positions */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Top 10 positions</CardTitle>
          <CardDescription>Répartition par actif</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveBar
              data={allocationByAssetData}
              keys={['value']}
              indexBy="name"
              theme={theme}
              margin={{ top: 8, right: 16, bottom: 40, left: 48 }}
              padding={0.3}
              colors={() => color('--chart-1')}
              borderRadius={4}
              enableLabel={false}
              enableGridY
              enableGridX={false}
              axisBottom={{ tickSize: 0, tickPadding: 8 }}
              axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}%` }}
              valueScale={{ type: 'linear' }}
              tooltip={({ indexValue, value }) => (
                <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                  <p className="text-xs text-muted-foreground">{indexValue}</p>
                  <p className="mt-0.5 font-mono text-sm tabular-nums">{value}%</p>
                </div>
              )}
              animate
              motionConfig="gentle"
            />
          </div>
        </CardContent>
      </Card>
    </>
  )
}
