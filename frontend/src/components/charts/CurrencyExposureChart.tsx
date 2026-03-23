import { memo, useMemo } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { formatCurrency } from '@/lib/utils'
import { AlertTriangle } from 'lucide-react'

interface CurrencyExposureItem {
  currency: string
  value: number
  percentage: number
}

interface CurrencyExposureChartProps {
  data: CurrencyExposureItem[]
  /** Threshold (%) above which a USD alert is shown */
  usdAlertThreshold?: number
}

const COLORS: Record<string, string> = {
  EUR: '#6366F1',
  USD: '#22C55E',
  GBP: '#F59E0B',
  CHF: '#EF4444',
  JPY: '#EC4899',
  CAD: '#8B5CF6',
  AUD: '#14B8A6',
  SEK: '#F97316',
  NOK: '#06B6D4',
  DKK: '#84CC16',
}

const DEFAULT_COLOR = '#64748B'

export default memo(function CurrencyExposureChart({
  data,
  usdAlertThreshold = 70,
}: CurrencyExposureChartProps) {
  const chartData = useMemo(
    () =>
      (data || []).map((item) => ({
        name: item.currency,
        value: item.value,
        percentage: item.percentage,
        color: COLORS[item.currency] || DEFAULT_COLOR,
      })),
    [data]
  )

  const usdExposure = useMemo(
    () => data?.find((d) => d.currency === 'USD')?.percentage ?? 0,
    [data]
  )

  if (!data || data.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean
    payload?: Array<{ payload: { name: string; value: number; percentage: number } }>
  }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-popover border rounded-lg shadow-lg p-3">
          <p className="font-medium">{data.name}</p>
          <p className="text-sm text-muted-foreground">{formatCurrency(data.value)}</p>
          <p className="text-sm text-muted-foreground">{data.percentage.toFixed(1)}%</p>
        </div>
      )
    }
    return null
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <defs>
            <filter id="ccyGlow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={90}
            paddingAngle={2}
            dataKey="value"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={1}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value, entry) => {
              const percentage = (
                entry as { payload?: { percentage: number } }
              ).payload?.percentage
              return (
                <span className="text-sm">
                  {value} ({percentage?.toFixed(1)}%)
                </span>
              )
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      {usdExposure > usdAlertThreshold && (
        <div className="flex items-center gap-2 mt-2 p-2 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            Exposition USD {usdExposure.toFixed(0)}% — risque de change significatif.
            Diversifiez en EUR pour limiter l'impact des fluctuations dollar.
          </span>
        </div>
      )}
    </div>
  )
})
