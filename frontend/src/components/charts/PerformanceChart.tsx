import { memo, useId, useMemo } from 'react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency } from '@/lib/utils'
import { useNivoTheme } from './nivo-theme'

interface DataPoint {
  date: string
  full_date?: string
  value: number
  invested?: number
  net_capital?: number
  gain_loss?: number
}

interface PerformanceChartProps {
  data: DataPoint[]
  color?: string
  period?: number
}

/** Accept either a raw color or an `oklch(var(--token))` string and resolve to rgb. */
function resolveColor(input: string, colorFn: (name: string) => string): string {
  const m = input.match(/var\((--[\w-]+)\)/)
  return m ? colorFn(m[1]) : input
}

const formatYAxis = (value: number) => {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M€`
  if (value >= 1000) return `${(value / 1000).toFixed(0)}k€`
  return `${value.toFixed(0)}€`
}

export default memo(function PerformanceChart({
  data,
  color = 'oklch(var(--chart-2))',
  period: _period = 30,
}: PerformanceChartProps) {
  const uid = useId().replace(/:/g, '')
  const reduceMotion = useReducedMotion()
  const { theme, color: tokenColor } = useNivoTheme()

  const valueColor = resolveColor(color, tokenColor)
  const investedColor = tokenColor('--muted-foreground')
  const netCapitalColor = tokenColor('--chart-1')

  const hasInvested = data?.some((d) => d.invested != null && d.invested > 0) ?? false
  const hasNetCapital = data?.some((d) => d.net_capital != null && d.net_capital > 0) ?? false

  const { minValue, maxValue } = useMemo(() => {
    if (!data || data.length === 0) return { minValue: 0, maxValue: 100 }
    const allValues = data.flatMap((d) => {
      const vals = [d.value]
      if (d.invested != null) vals.push(d.invested)
      if (d.net_capital != null) vals.push(d.net_capital)
      return vals
    })
    const min = Math.min(...allValues)
    const max = Math.max(...allValues)
    const range = max - min || max || 1
    return { minValue: Math.max(0, min - range * 0.1), maxValue: max + range * 0.1 }
  }, [data])

  const series = useMemo<LineSeries[]>(
    () => [
      {
        id: 'value',
        data: (data || []).map((d) => ({ x: d.date, y: d.value })),
      },
    ],
    [data]
  )

  // Show ~6 evenly spaced x labels regardless of point count.
  const tickValues = useMemo(() => {
    if (!data || data.length === 0) return []
    const target = Math.min(6, data.length)
    const step = Math.max(1, Math.floor(data.length / target))
    return data.filter((_, i) => i % step === 0).map((d) => d.date)
  }, [data])

  if (!data || data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  // Custom layer drawing the dashed reference lines (invested / net_capital),
  // positioned with the chart's own scales so they share the value axis.
  const ReferenceLines = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
    const buildPath = (key: 'invested' | 'net_capital') =>
      data
        .filter((d) => d[key] != null)
        .map((d, i) => `${i === 0 ? 'M' : 'L'}${xScale(d.date)},${yScale(d[key] as number)}`)
        .join(' ')

    return (
      <>
        {hasInvested && (
          <path
            d={buildPath('invested')}
            fill="none"
            stroke={investedColor}
            strokeWidth={1.5}
            strokeDasharray="6 3"
          />
        )}
        {hasNetCapital && (
          <path
            d={buildPath('net_capital')}
            fill="none"
            stroke={netCapitalColor}
            strokeWidth={1.5}
            strokeDasharray="3 3"
          />
        )}
      </>
    )
  }

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="h-[300px]">
        <ResponsiveLine
          data={series}
          theme={theme}
          margin={{ top: 12, right: 14, bottom: 28, left: 58 }}
          xScale={{ type: 'point' }}
          yScale={{ type: 'linear', min: minValue, max: maxValue, stacked: false }}
          curve="monotoneX"
          colors={[valueColor]}
          lineWidth={2}
          enablePoints={false}
          enableGridX={false}
          enableArea
          areaOpacity={1}
          defs={[
            {
              id: `${uid}-fill`,
              type: 'linearGradient',
              colors: [
                { offset: 0, color: valueColor, opacity: 0.2 },
                { offset: 100, color: valueColor, opacity: 0 },
              ],
            },
          ]}
          fill={[{ match: '*', id: `${uid}-fill` }]}
          axisBottom={{ tickSize: 0, tickPadding: 8, tickValues }}
          axisLeft={{ tickSize: 0, tickPadding: 6, format: formatYAxis }}
          enableSlices="x"
          layers={[
            'grid',
            'markers',
            'areas',
            ReferenceLines,
            'lines',
            'slices',
            'axes',
            'points',
            'mesh',
          ]}
          sliceTooltip={({ slice }) => {
            const x = slice.points[0]?.data.x
            const point = data.find((d) => d.date === x)
            if (!point) return null
            const formattedDate = point.full_date
              ? new Date(point.full_date).toLocaleDateString('fr-FR', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })
              : point.date
            const rows: Array<{ label: string; value: number; color: string }> = [
              { label: 'Valeur', value: point.value, color: valueColor },
            ]
            if (hasInvested && point.invested != null)
              rows.push({ label: 'Total investi', value: point.invested, color: investedColor })
            if (hasNetCapital && point.net_capital != null)
              rows.push({ label: 'Capital net', value: point.net_capital, color: netCapitalColor })
            return (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                <p className="mb-1.5 text-xs capitalize text-muted-foreground">{formattedDate}</p>
                {rows.map((r) => (
                  <div key={r.label} className="flex items-center justify-between gap-4">
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-[2px]"
                        style={{ backgroundColor: r.color }}
                      />
                      <span className="text-xs text-muted-foreground">{r.label}</span>
                    </span>
                    <span className="font-mono text-sm tabular-nums">{formatCurrency(r.value)}</span>
                  </div>
                ))}
                {point.gain_loss != null && (
                  <div
                    className={`mt-1.5 flex items-center justify-between gap-4 border-t border-border pt-1.5 text-xs ${
                      point.gain_loss >= 0 ? 'text-gain' : 'text-loss'
                    }`}
                  >
                    <span>Plus/moins-value</span>
                    <span className="font-mono tabular-nums">{formatCurrency(point.gain_loss)}</span>
                  </div>
                )}
              </div>
            )
          }}
          animate={!reduceMotion}
          motionConfig="gentle"
        />
      </div>
    </motion.div>
  )
})
