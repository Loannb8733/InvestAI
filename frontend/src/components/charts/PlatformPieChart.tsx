import { memo, useMemo, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip, Sector } from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, PlatformDistributionItem } from '@/services/api'
import { formatCurrency } from '@/lib/utils'
import { getTrustColor, getTrustLabel, getTrustScore } from '@/lib/platforms'
import { Loader2, Shield } from 'lucide-react'

interface PlatformPieChartProps {
  onPlatformClick?: (platform: string | null) => void
}

export default memo(function PlatformPieChart({ onPlatformClick }: PlatformPieChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | undefined>(undefined)

  const { data, isLoading } = useQuery({
    queryKey: ['platform-distribution'],
    queryFn: () => analyticsApi.getPlatformDistribution(),
    staleTime: 60_000,
  })

  const chartData = useMemo(() =>
    (data || []).map((item: PlatformDistributionItem) => ({
      ...item,
      color: getTrustColor(item.trust_score ?? getTrustScore(item.name)),
    })),
  [data])

  if (isLoading) {
    return (
      <div className="h-[300px] flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  if (!chartData.length) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: { name: string; value: number; percentage: number; trust_score: number } }> }) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      const score = d.trust_score ?? getTrustScore(d.name)
      return (
        <div className="bg-popover border rounded-lg shadow-lg p-3">
          <p className="font-medium">{d.name}</p>
          <p className="text-sm text-muted-foreground">{formatCurrency(d.value)}</p>
          <p className="text-sm text-muted-foreground">{d.percentage.toFixed(1)}%</p>
          <div className="flex items-center gap-1 mt-1">
            <Shield className="h-3 w-3" style={{ color: getTrustColor(score) }} />
            <span className="text-xs" style={{ color: getTrustColor(score) }}>
              {getTrustLabel(score)} ({score}/10)
            </span>
          </div>
        </div>
      )
    }
    return null
  }

  const renderActiveShape = (props: unknown) => {
    const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props as {
      cx: number; cy: number; innerRadius: number; outerRadius: number
      startAngle: number; endAngle: number; fill: string
    }
    return (
      <Sector
        cx={cx} cy={cy}
        innerRadius={innerRadius} outerRadius={(outerRadius as number) + 6}
        startAngle={startAngle} endAngle={endAngle}
        fill={fill}
      />
    )
  }

  const handleClick = (_: unknown, index: number) => {
    if (!onPlatformClick) return
    if (activeIndex === index) {
      setActiveIndex(undefined)
      onPlatformClick(null)
    } else {
      setActiveIndex(index)
      onPlatformClick(chartData[index].name)
    }
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          dataKey="value"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth={1}
          activeIndex={activeIndex}
          activeShape={renderActiveShape}
          onClick={handleClick}
          className="cursor-pointer"
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          onClick={(e) => {
            const idx = chartData.findIndex((d) => d.name === e.value)
            if (idx >= 0) handleClick(null, idx)
          }}
          className="cursor-pointer"
          formatter={(value, entry) => {
            const pld = (entry as { payload?: { percentage: number; trust_score: number } }).payload
            return (
              <span className="text-sm">
                {value} ({pld?.percentage?.toFixed(1)}%)
              </span>
            )
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
})
