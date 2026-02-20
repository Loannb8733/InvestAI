import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  LineChart,
  Line,
  XAxis as RXAxis,
  YAxis as RYAxis,
  CartesianGrid as RCartesianGrid,
  Tooltip as RTooltip,
  ResponsiveContainer,
  Legend as RLegend,
} from 'recharts'

interface BenchmarkSeries {
  name: string
  symbol: string
  data: Array<{ date: string; value: number }>
}

interface DashboardBenchmarkChartProps {
  benchmarks: BenchmarkSeries[]
}

const BENCH_COLORS = ['#3b82f6', '#f59e0b', '#8b5cf6', '#22c55e']

export default function DashboardBenchmarkChart({ benchmarks }: DashboardBenchmarkChartProps) {
  // Merge all series into one dataset keyed by date
  const dateMap: Record<string, Record<string, number>> = {}
  benchmarks.forEach((series) => {
    series.data.forEach((p) => {
      if (!dateMap[p.date]) dateMap[p.date] = {}
      dateMap[p.date][series.symbol] = p.value
    })
  })
  const chartData = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date: date.slice(5), ...vals }))

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Performance comparée (base 100)</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
            <RCartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
            <RXAxis dataKey="date" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} tickLine={false} axisLine={false} />
            <RYAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
            <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--popover))', borderColor: 'hsl(var(--border))', color: 'hsl(var(--popover-foreground))', borderRadius: '0.5rem', fontSize: 12 }} />
            <RLegend verticalAlign="top" height={30} wrapperStyle={{ fontSize: 12 }} />
            {benchmarks.map((series, i) => (
              <Line key={series.symbol} type="monotone" dataKey={series.symbol} name={series.name} stroke={BENCH_COLORS[i % BENCH_COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
