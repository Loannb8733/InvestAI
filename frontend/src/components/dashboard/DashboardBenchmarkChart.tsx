import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ResponsiveLine, type LineSeries } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'

interface BenchmarkSeries {
  name: string
  symbol: string
  data: Array<{ date: string; value: number }>
}

interface DashboardBenchmarkChartProps {
  benchmarks: BenchmarkSeries[]
}

const BENCH_TOKENS = ['--chart-5', '--chart-1', '--chart-2', '--chart-3']

export default function DashboardBenchmarkChart({ benchmarks }: DashboardBenchmarkChartProps) {
  const { theme, color } = useNivoTheme()

  const colorBySymbol = useMemo(() => {
    const map: Record<string, string> = {}
    benchmarks.forEach((s, i) => {
      map[s.symbol] = color(BENCH_TOKENS[i % BENCH_TOKENS.length])
    })
    return map
  }, [benchmarks, color])

  const series = useMemo<LineSeries[]>(
    () =>
      benchmarks.map((s) => ({
        id: s.symbol,
        data: s.data.map((p) => ({ x: p.date.slice(5), y: p.value })),
      })),
    [benchmarks]
  )

  const tickValues = useMemo(() => {
    const longest = benchmarks.reduce(
      (acc, s) => (s.data.length > acc.length ? s.data : acc),
      [] as BenchmarkSeries['data']
    )
    if (longest.length === 0) return []
    const target = Math.min(6, longest.length)
    const step = Math.max(1, Math.floor(longest.length / target))
    return longest.filter((_, i) => i % step === 0).map((p) => p.date.slice(5))
  }, [benchmarks])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Performance comparée (base 100)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[250px]">
          <ResponsiveLine
            data={series}
            theme={theme}
            margin={{ top: 28, right: 16, bottom: 28, left: 44 }}
            xScale={{ type: 'point' }}
            yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
            curve="monotoneX"
            colors={(s) => colorBySymbol[s.id as string]}
            lineWidth={2}
            enablePoints={false}
            enableGridX={false}
            axisBottom={{ tickSize: 0, tickPadding: 8, tickValues }}
            axisLeft={{ tickSize: 0, tickPadding: 6 }}
            enableSlices="x"
            sliceTooltip={({ slice }) => (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                <p className="mb-1.5 text-xs text-muted-foreground">{slice.points[0]?.data.x as string}</p>
                {slice.points.map((p) => {
                  const name = benchmarks.find((b) => b.symbol === p.seriesId)?.name ?? p.seriesId
                  return (
                    <div key={p.id} className="flex items-center justify-between gap-4">
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 rounded-[2px]"
                          style={{ backgroundColor: colorBySymbol[p.seriesId as string] }}
                        />
                        <span className="text-xs text-muted-foreground">{name}</span>
                      </span>
                      <span className="font-mono text-sm tabular-nums">
                        {(p.data.y as number).toFixed(1)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
            legends={[
              {
                anchor: 'top-right',
                direction: 'row',
                translateY: -22,
                itemWidth: 90,
                itemHeight: 18,
                symbolSize: 10,
                symbolShape: 'circle',
                itemTextColor: color('--muted-foreground'),
                data: benchmarks.map((s) => ({
                  id: s.symbol,
                  label: s.name,
                  color: colorBySymbol[s.symbol],
                })),
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
