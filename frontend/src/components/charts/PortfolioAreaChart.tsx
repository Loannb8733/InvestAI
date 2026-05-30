import { memo, useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  AreaSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type MouseEventParams,
} from 'lightweight-charts'
import { motion, useReducedMotion } from 'framer-motion'
import { useTheme } from '@/components/theme-provider'
import { formatCurrency } from '@/lib/utils'
import { resolveChartTheme } from './lightweight-theme'

interface DataPoint {
  date: string
  full_date?: string
  value: number
  invested?: number
  net_capital?: number
  gain_loss?: number
}

interface PortfolioAreaChartProps {
  data: DataPoint[]
  period?: number
}

interface SeriesPoint {
  time: UTCTimestamp
  value: number
}

// The API feeds us a display `date` plus an ISO `full_date`. Lightweight
// Charts needs ascending, unique UNIX-second timestamps — so we key off
// full_date when present and dedupe (keeping the last reading for a day).
function toSeries(data: DataPoint[]): {
  value: SeriesPoint[]
  invested: SeriesPoint[]
  byTime: Map<number, DataPoint>
} {
  const byTime = new Map<number, DataPoint>()
  for (const d of data) {
    const raw = d.full_date ?? d.date
    const ms = Date.parse(raw)
    if (Number.isNaN(ms)) continue
    const time = Math.floor(ms / 1000)
    byTime.set(time, d)
  }
  const times = [...byTime.keys()].sort((a, b) => a - b)
  const value: SeriesPoint[] = []
  const invested: SeriesPoint[] = []
  for (const time of times) {
    const d = byTime.get(time)!
    value.push({ time: time as UTCTimestamp, value: d.value })
    if (d.invested != null && d.invested > 0) {
      invested.push({ time: time as UTCTimestamp, value: d.invested })
    }
  }
  return { value, invested, byTime }
}

export default memo(function PortfolioAreaChart({ data }: PortfolioAreaChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const areaRef = useRef<ISeriesApi<'Area'> | null>(null)
  const investedRef = useRef<ISeriesApi<'Line'> | null>(null)
  const { theme } = useTheme()
  const reduceMotion = useReducedMotion()

  const { value, invested, byTime } = useMemo(() => toSeries(data), [data])
  const hasInvested = invested.length > 0

  const [tooltip, setTooltip] = useState<{
    x: number
    point: DataPoint
  } | null>(null)

  // Creation effect — rebuild when the theme flips so resolved OKLCH tokens
  // (which read the live `.dark` class) stay in sync.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const t = resolveChartTheme('--chart-1')
    const chart = createChart(container, t.options)
    chartRef.current = chart

    const area = chart.addSeries(AreaSeries, {
      lineColor: t.area.lineColor,
      topColor: t.area.topColor,
      bottomColor: t.area.bottomColor,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: t.markerBorder,
      priceFormat: { type: 'custom', formatter: (p: number) => formatCurrency(p) },
    })
    areaRef.current = area

    const investedLine = chart.addSeries(LineSeries, {
      color: t.invested.color,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    investedRef.current = investedLine

    const onMove = (param: MouseEventParams) => {
      if (
        !param.time ||
        param.point === undefined ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setTooltip(null)
        return
      }
      const time = param.time as number
      const point = byTime.get(time)
      if (!point) {
        setTooltip(null)
        return
      }
      setTooltip({ x: param.point.x, point })
    }
    chart.subscribeCrosshairMove(onMove)

    return () => {
      chart.unsubscribeCrosshairMove(onMove)
      chart.remove()
      chartRef.current = null
      areaRef.current = null
      investedRef.current = null
    }
    // byTime is derived from data; re-running the creation effect on every data
    // change would thrash the canvas, so the data effect below owns updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme])

  // Data effect — push new points without recreating the chart.
  useEffect(() => {
    if (!areaRef.current || !investedRef.current) return
    areaRef.current.setData(value)
    investedRef.current.setData(hasInvested ? invested : [])
    chartRef.current?.timeScale().fitContent()
  }, [value, invested, hasInvested])

  if (!data || data.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm">
        Aucune donnée disponible
      </div>
    )
  }

  const tip = tooltip?.point
  const formattedDate = tip?.full_date
    ? new Date(tip.full_date).toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : tip?.date

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="relative"
    >
      <div ref={containerRef} className="h-[300px] w-full" />

      {tip && (
        <div
          className="pointer-events-none absolute top-2 z-10 max-w-[240px] -translate-x-1/2 rounded-lg border border-border bg-popover px-3 py-2 shadow-md"
          style={{
            left: Math.min(Math.max(tooltip!.x, 90), (containerRef.current?.clientWidth ?? 0) - 90),
          }}
        >
          <p className="text-xs text-muted-foreground capitalize mb-1.5">{formattedDate}</p>
          <div className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-[2px] bg-[oklch(var(--chart-1))]" />
              <span className="text-xs text-muted-foreground">Valeur</span>
            </span>
            <span className="font-mono tabular-nums text-sm">{formatCurrency(tip.value)}</span>
          </div>
          {tip.invested != null && tip.invested > 0 && (
            <div className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-[2px] bg-muted-foreground" />
                <span className="text-xs text-muted-foreground">Total investi</span>
              </span>
              <span className="font-mono tabular-nums text-sm">{formatCurrency(tip.invested)}</span>
            </div>
          )}
          {tip.gain_loss != null && (
            <div
              className={`flex items-center justify-between gap-4 text-xs mt-1.5 pt-1.5 border-t border-border ${
                tip.gain_loss >= 0 ? 'text-gain' : 'text-loss'
              }`}
            >
              <span>Plus/moins-value</span>
              <span className="font-mono tabular-nums">{formatCurrency(tip.gain_loss)}</span>
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
})
