import { useMemo } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { formatCurrency } from '@/lib/utils'

interface DataPoint {
  date: string
  full_date?: string
  value: number
  invested?: number
  net_capital?: number
  gain_loss?: number
  is_estimated?: boolean
}

interface PerformanceChartProps {
  data: DataPoint[]
  color?: string
  period?: number
}

export default function PerformanceChart({
  data,
  color = '#2563EB',
  period = 30,
}: PerformanceChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  const hasInvested = data.some(d => d.invested != null && d.invested > 0)
  const hasNetCapital = data.some(d => d.net_capital != null && d.net_capital > 0)

  // Calculate min/max for better Y-axis scaling
  const { minValue, maxValue } = useMemo(() => {
    const allValues = data.flatMap(d => {
      const vals = [d.value]
      if (d.invested != null) vals.push(d.invested)
      if (d.net_capital != null) vals.push(d.net_capital)
      return vals
    })
    const min = Math.min(...allValues)
    const max = Math.max(...allValues)
    const range = max - min
    const paddedMin = Math.max(0, min - range * 0.1)
    const paddedMax = max + range * 0.1
    return { minValue: paddedMin, maxValue: paddedMax }
  }, [data])

  // Determine how many X-axis labels to show based on data length
  const xAxisInterval = useMemo(() => {
    if (data.length <= 7) return 0
    if (data.length <= 14) return 1
    if (data.length <= 30) return Math.floor(data.length / 7) - 1
    if (data.length <= 60) return Math.floor(data.length / 6) - 1
    return Math.floor(data.length / 5) - 1
  }, [data.length])

  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; dataKey: string; color: string; payload: DataPoint }>; label?: string }) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload as DataPoint
      const formattedDate = point.full_date
        ? new Date(point.full_date).toLocaleDateString('fr-FR', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })
        : label

      const labelMap: Record<string, string> = {
        value: 'Valeur',
        invested: 'Total investi',
        net_capital: 'Capital net',
      }

      return (
        <div className="bg-popover border rounded-lg shadow-lg p-3">
          <p className="text-sm text-muted-foreground capitalize mb-1">{formattedDate}</p>
          {payload.map((entry, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
              <span className="text-xs text-muted-foreground">{labelMap[entry.dataKey] || entry.dataKey}:</span>
              <span className="font-medium text-sm">{formatCurrency(entry.value)}</span>
            </div>
          ))}
          {point.gain_loss != null && (
            <div className={`text-xs mt-1 pt-1 border-t ${point.gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              P/L: {formatCurrency(point.gain_loss)}
            </div>
          )}
          {point.is_estimated && (
            <p className="text-xs text-yellow-600 mt-1">* Valeur estimée</p>
          )}
        </div>
      )
    }
    return null
  }

  const formatYAxis = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M€`
    if (value >= 1000) return `${(value / 1000).toFixed(0)}k€`
    return `${value.toFixed(0)}€`
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart
        data={data}
        margin={{ top: 10, right: 10, left: 10, bottom: 0 }}
      >
        <defs>
          <linearGradient id={`colorValue-${period}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.2} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
        <XAxis
          dataKey="date"
          className="text-xs"
          tickLine={false}
          axisLine={false}
          interval={xAxisInterval}
          tick={{ fontSize: 11 }}
          dy={5}
        />
        <YAxis
          className="text-xs"
          tickLine={false}
          axisLine={false}
          tickFormatter={formatYAxis}
          domain={[minValue, maxValue]}
          tick={{ fontSize: 11 }}
          width={55}
        />
        <Tooltip content={<CustomTooltip />} />
        {(hasInvested || hasNetCapital) && (
          <Legend
            verticalAlign="top"
            height={30}
            formatter={(value: string) => {
              const labels: Record<string, string> = {
                value: 'Valeur',
                invested: 'Total investi',
                net_capital: 'Capital net',
              }
              return <span className="text-xs">{labels[value] || value}</span>
            }}
          />
        )}
        <Area
          type="monotone"
          dataKey="value"
          name="value"
          stroke={color}
          strokeWidth={2}
          fillOpacity={1}
          fill={`url(#colorValue-${period})`}
          dot={data.length <= 14}
          activeDot={{ r: 6, strokeWidth: 2, stroke: '#fff' }}
        />
        {hasInvested && (
          <Area
            type="monotone"
            dataKey="invested"
            name="invested"
            stroke="#94a3b8"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            fillOpacity={0}
            dot={false}
          />
        )}
        {hasNetCapital && (
          <Area
            type="monotone"
            dataKey="net_capital"
            name="net_capital"
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            fillOpacity={0}
            dot={false}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}
