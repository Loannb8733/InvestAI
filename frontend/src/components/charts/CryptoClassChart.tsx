import { memo, useMemo } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { formatCurrency } from '@/lib/utils'
import {
  CRYPTO_ASSET_CLASSES,
  CRYPTO_CLASS_LABELS,
  CRYPTO_CLASS_COLORS,
  MIN_DISPLAY_VALUE,
} from '@/lib/constants'

interface AssetAllocation {
  symbol: string
  asset_type: string
  value: number
  percentage: number
}

interface CryptoClassChartProps {
  assets: AssetAllocation[]
}

export default memo(function CryptoClassChart({ assets }: CryptoClassChartProps) {
  const chartData = useMemo(() => {
    const cryptoAssets = assets.filter(
      (a) => a.asset_type === 'crypto' && a.value >= MIN_DISPLAY_VALUE
    )

    if (cryptoAssets.length === 0) return []

    const totalCryptoValue = cryptoAssets.reduce((sum, a) => sum + a.value, 0)
    const classTotals: Record<string, number> = {}

    for (const asset of cryptoAssets) {
      const cls = CRYPTO_ASSET_CLASSES[asset.symbol.toUpperCase()] || 'Other'
      classTotals[cls] = (classTotals[cls] || 0) + asset.value
    }

    return Object.entries(classTotals)
      .map(([cls, value]) => ({
        name: CRYPTO_CLASS_LABELS[cls] || cls,
        value,
        percentage: totalCryptoValue > 0 ? (value / totalCryptoValue) * 100 : 0,
        color: CRYPTO_CLASS_COLORS[cls] || CRYPTO_CLASS_COLORS.Other,
      }))
      .sort((a, b) => b.value - a.value)
  }, [assets])

  if (chartData.length === 0) {
    return (
      <div className="h-[250px] flex items-center justify-center text-muted-foreground text-sm">
        Aucun actif crypto
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
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={85}
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
  )
})
