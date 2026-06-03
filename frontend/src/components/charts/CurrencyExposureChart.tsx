import { memo, useMemo } from 'react'
import { ResponsivePie } from '@nivo/pie'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency } from '@/lib/utils'
import { AlertTriangle } from 'lucide-react'
import { useNivoTheme } from './nivo-theme'

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

const TOKENS: Record<string, string> = {
  EUR: '--chart-2',
  USD: '--chart-3',
  GBP: '--chart-1',
  CHF: '--chart-4',
  JPY: '--chart-2',
  CAD: '--chart-2',
  AUD: '--chart-3',
  SEK: '--chart-1',
  NOK: '--chart-5',
  DKK: '--chart-3',
}

export default memo(function CurrencyExposureChart({
  data,
  usdAlertThreshold = 70,
}: CurrencyExposureChartProps) {
  const reduceMotion = useReducedMotion()
  const { theme, color } = useNivoTheme()

  const chartData = useMemo(
    () =>
      (data || []).map((item) => ({
        id: item.currency,
        label: item.currency,
        value: item.value,
        percentage: item.percentage,
        color: color(TOKENS[item.currency] || '--muted-foreground'),
      })),
    [data, color]
  )

  const usdExposure = useMemo(
    () => data?.find((d) => d.currency === 'USD')?.percentage ?? 0,
    [data]
  )

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
      <div className="relative h-[240px]">
        <ResponsivePie
          data={chartData}
          theme={theme}
          margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
          innerRadius={0.64}
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

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
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

      {usdExposure > usdAlertThreshold && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-warning/10 p-2 text-xs text-warning">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            Exposition USD {usdExposure.toFixed(0)}% — risque de change significatif.
            Diversifiez en EUR pour limiter l'impact des fluctuations dollar.
          </span>
        </div>
      )}
    </motion.div>
  )
})
