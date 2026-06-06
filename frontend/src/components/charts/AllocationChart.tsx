import { memo, useMemo, useState } from 'react'
import { ResponsivePie } from '@nivo/pie'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency } from '@/lib/utils'
import { useNivoTheme } from './nivo-theme'

interface AllocationItem {
  type: string
  value: number
  percentage: number
}

interface AllocationChartProps {
  data: AllocationItem[]
}

const TOKENS: Record<string, string> = {
  crypto: '--chart-1',
  stock: '--chart-2',
  crowdfunding: '--chart-3',
  real_estate: '--chart-4',
  etf: '--chart-5',
  bond: '--chart-2',
  other: '--muted-foreground',
}

const LABELS: Record<string, string> = {
  crypto: 'Crypto',
  stock: 'Actions',
  etf: 'ETF',
  real_estate: 'Immobilier',
  bond: 'Obligations',
  crowdfunding: 'Crowdfunding',
  other: 'Autres',
}

export default memo(function AllocationChart({ data }: AllocationChartProps) {
  const reduceMotion = useReducedMotion()
  const { theme, color } = useNivoTheme()
  const [activeId, setActiveId] = useState<string | null>(null)

  const chartData = useMemo(
    () =>
      (data || []).map((item) => ({
        id: LABELS[item.type] || item.type,
        label: LABELS[item.type] || item.type,
        value: item.value,
        percentage: item.percentage,
        color: color(TOKENS[item.type] || '--muted-foreground'),
      })),
    [data, color]
  )

  const total = useMemo(() => chartData.reduce((sum, d) => sum + d.value, 0), [chartData])

  if (!data || data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <div
        className="relative h-[260px]"
        role="img"
        aria-label={
          chartData.length === 0
            ? 'Allocation par classe d’actifs : aucune donnée'
            : `Allocation par classe d’actifs : ${chartData
                .map((d) => `${d.label} ${Math.round((d.value / Math.max(total, 1)) * 100)}%`)
                .join(', ')}`
        }
      >
        <ResponsivePie
          data={chartData}
          theme={theme}
          margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
          innerRadius={0.66}
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
          onActiveIdChange={(id) => setActiveId(id != null ? String(id) : null)}
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

        {/* Center total */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xs uppercase tracking-wider text-muted-foreground">Total</span>
          <span className="font-serif text-xl font-medium tabular-nums tracking-tight">
            {formatCurrency(total)}
          </span>
        </div>
      </div>

      {/* Editorial legend */}
      <div className="mt-5 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {chartData.map((entry) => (
          <div
            key={entry.id}
            className={`flex items-center justify-between gap-3 rounded-md px-1.5 py-1 transition-colors ${
              activeId === entry.id ? 'bg-muted' : ''
            }`}
          >
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
