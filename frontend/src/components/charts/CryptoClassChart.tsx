import { memo, useMemo } from 'react'
import { ResponsivePie } from '@nivo/pie'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency } from '@/lib/utils'
import {
  CRYPTO_ASSET_CLASSES,
  CRYPTO_CLASS_LABELS,
  CRYPTO_CLASS_COLORS,
  MIN_DISPLAY_VALUE,
} from '@/lib/constants'
import { useNivoTheme } from './nivo-theme'

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
  const reduceMotion = useReducedMotion()
  const { theme, color } = useNivoTheme()

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
        id: CRYPTO_CLASS_LABELS[cls] || cls,
        label: CRYPTO_CLASS_LABELS[cls] || cls,
        value,
        percentage: totalCryptoValue > 0 ? (value / totalCryptoValue) * 100 : 0,
        color: CRYPTO_CLASS_COLORS[cls] || CRYPTO_CLASS_COLORS.Other,
      }))
      .sort((a, b) => b.value - a.value)
  }, [assets])

  if (chartData.length === 0) {
    return (
      <div className="flex h-[250px] items-center justify-center text-sm text-muted-foreground">
        Aucun actif crypto
      </div>
    )
  }

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="relative h-[220px]">
        <ResponsivePie
          data={chartData}
          theme={theme}
          margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
          innerRadius={0.62}
          padAngle={1.4}
          cornerRadius={3}
          colors={{ datum: 'data.color' }}
          borderWidth={2}
          borderColor={color('--background')}
          enableArcLabels={false}
          enableArcLinkLabels={false}
          activeOuterRadiusOffset={6}
          activeInnerRadiusOffset={2}
          isInteractive
          animate={!reduceMotion}
          motionConfig="gentle"
          tooltip={({ datum }) => (
            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
              <p className="text-sm font-medium">{datum.label}</p>
              <p className="mt-0.5 font-mono text-sm tabular-nums">{formatCurrency(datum.value)}</p>
              <p className="font-mono text-xs tabular-nums text-muted-foreground">
                {(datum.data as { percentage: number }).percentage.toFixed(1)}%
              </p>
            </div>
          )}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2">
        {chartData.map((entry) => (
          <div key={entry.id} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
                style={{ background: entry.color }}
              />
              <span className="truncate text-sm">{entry.label}</span>
            </span>
            <span className="font-mono text-sm tabular-nums text-muted-foreground">
              {entry.percentage.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  )
})
