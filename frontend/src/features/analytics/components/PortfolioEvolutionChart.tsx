import { useId, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import { ResponsiveLine, type LineSeries } from '@nivo/line'
import { LineChart as LineChartIcon } from 'lucide-react'
import { useNivoTheme } from '@/components/charts/nivo-theme'

interface ChartDataPoint {
  date: string
  fullDate: string
  value: number
  invested: number
  gain: number
}

interface PortfolioEvolutionChartProps {
  chartHistoricalData: ChartDataPoint[]
}

const LABELS: Record<string, string> = {
  value: 'Valeur actuelle',
  invested: 'Montant investi',
}

export default function PortfolioEvolutionChart({ chartHistoricalData }: PortfolioEvolutionChartProps) {
  const uid = useId().replace(/:/g, '')
  const { theme, color } = useNivoTheme()

  const seriesColors = useMemo(
    () => ({ value: color('--chart-5'), invested: color('--muted-foreground') }),
    [color]
  )

  const series = useMemo<LineSeries[]>(
    () => [
      {
        id: 'invested',
        data: chartHistoricalData.map((d) => ({ x: d.date, y: d.invested })),
      },
      {
        id: 'value',
        data: chartHistoricalData.map((d) => ({ x: d.date, y: d.value })),
      },
    ],
    [chartHistoricalData]
  )

  const tickValues = useMemo(() => {
    if (chartHistoricalData.length === 0) return []
    const target = Math.min(6, chartHistoricalData.length)
    const step = Math.max(1, Math.floor(chartHistoricalData.length / target))
    return chartHistoricalData.filter((_, i) => i % step === 0).map((d) => d.date)
  }, [chartHistoricalData])

  if (chartHistoricalData.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LineChartIcon className="h-5 w-5" />
          Évolution du portefeuille
        </CardTitle>
        <CardDescription>Valeur totale vs montant investi</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72">
          <ResponsiveLine
            data={series}
            theme={theme}
            margin={{ top: 28, right: 16, bottom: 28, left: 64 }}
            xScale={{ type: 'point' }}
            yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
            curve="monotoneX"
            colors={(s) => seriesColors[s.id as 'value' | 'invested']}
            lineWidth={2}
            enablePoints={false}
            enableGridX={false}
            enableArea
            areaOpacity={1}
            defs={[
              {
                id: `${uid}-value`,
                type: 'linearGradient',
                colors: [
                  { offset: 0, color: seriesColors.value, opacity: 0.3 },
                  { offset: 100, color: seriesColors.value, opacity: 0 },
                ],
              },
              {
                id: `${uid}-invested`,
                type: 'linearGradient',
                colors: [
                  { offset: 0, color: seriesColors.invested, opacity: 0.25 },
                  { offset: 100, color: seriesColors.invested, opacity: 0 },
                ],
              },
            ]}
            fill={[
              { match: { id: 'value' }, id: `${uid}-value` },
              { match: { id: 'invested' }, id: `${uid}-invested` },
            ]}
            axisBottom={{ tickSize: 0, tickPadding: 8, tickValues }}
            axisLeft={{
              tickSize: 0,
              tickPadding: 6,
              format: (v) => formatCurrency(v as number).replace('€', ''),
            }}
            enableSlices="x"
            sliceTooltip={({ slice }) => (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                <p className="mb-1.5 text-xs text-muted-foreground">{slice.points[0]?.data.x as string}</p>
                {slice.points.map((p) => (
                  <div key={p.id} className="flex items-center justify-between gap-4">
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-[2px]"
                        style={{ backgroundColor: seriesColors[p.seriesId as 'value' | 'invested'] }}
                      />
                      <span className="text-xs text-muted-foreground">
                        {LABELS[p.seriesId as string] ?? p.seriesId}
                      </span>
                    </span>
                    <span className="font-mono text-sm tabular-nums">
                      {formatCurrency(p.data.y as number)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            legends={[
              {
                anchor: 'top-right',
                direction: 'row',
                translateY: -22,
                itemWidth: 120,
                itemHeight: 18,
                symbolSize: 10,
                symbolShape: 'circle',
                itemTextColor: color('--muted-foreground'),
                data: [
                  { id: 'value', label: LABELS.value, color: seriesColors.value },
                  { id: 'invested', label: LABELS.invested, color: seriesColors.invested },
                ],
              },
            ]}
            animate
            motionConfig="gentle"
          />
        </div>
      </CardContent>
    </Card>
  )
}
