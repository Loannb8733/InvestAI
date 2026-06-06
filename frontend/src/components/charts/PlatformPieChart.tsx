import { memo, useMemo, useState } from 'react'
import { ResponsivePie } from '@nivo/pie'
import { motion, useReducedMotion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, PlatformDistributionItem } from '@/services/api'
import { formatCurrency } from '@/lib/utils'
import { getTrustColor, getTrustLabel, getTrustScore } from '@/lib/platforms'
import { Loader2, Shield } from 'lucide-react'
import { useNivoTheme } from './nivo-theme'

interface PlatformPieChartProps {
  onPlatformClick?: (platform: string | null) => void
}

export default memo(function PlatformPieChart({ onPlatformClick }: PlatformPieChartProps) {
  const reduceMotion = useReducedMotion()
  const { theme, color } = useNivoTheme()
  const [activeName, setActiveName] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['platform-distribution'],
    queryFn: () => analyticsApi.getPlatformDistribution(),
    staleTime: 60_000,
  })

  const chartData = useMemo(
    () =>
      (data || []).map((item: PlatformDistributionItem) => {
        const score = item.trust_score ?? getTrustScore(item.name)
        return {
          id: item.name,
          label: item.name,
          value: item.value,
          percentage: item.percentage,
          trustScore: score,
          color: getTrustColor(score),
        }
      }),
    [data]
  )

  if (isLoading) {
    return (
      <div className="flex h-[300px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  if (!chartData.length) {
    return (
      <div className="flex h-[300px] items-center justify-center text-muted-foreground">
        Aucune donnée disponible
      </div>
    )
  }

  const toggle = (name: string) => {
    if (!onPlatformClick) return
    if (activeName === name) {
      setActiveName(null)
      onPlatformClick(null)
    } else {
      setActiveName(name)
      onPlatformClick(name)
    }
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
        aria-label={`Répartition par plateforme : ${chartData
          .map((d) => `${d.id} ${Math.round(d.value)}€`)
          .join(', ')}`}
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
          onActiveIdChange={(id) => setActiveName(id != null ? String(id) : null)}
          onClick={(node) => toggle(String(node.id))}
          animate={!reduceMotion}
          motionConfig="gentle"
          tooltip={({ datum }) => {
            const score = (datum.data as { trustScore: number }).trustScore
            return (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                <p className="text-sm font-medium">{datum.label}</p>
                <p className="mt-0.5 font-mono text-sm tabular-nums">{formatCurrency(datum.value)}</p>
                <p className="font-mono text-xs tabular-nums text-muted-foreground">
                  {(datum.data as { percentage: number }).percentage.toFixed(1)}%
                </p>
                <div className="mt-1 flex items-center gap-1">
                  <Shield className="h-3 w-3" style={{ color: getTrustColor(score) }} />
                  <span className="text-xs" style={{ color: getTrustColor(score) }}>
                    {getTrustLabel(score)} ({score}/10)
                  </span>
                </div>
              </div>
            )
          }}
        />
      </div>

      {/* Editorial legend — click to filter */}
      <div className="mt-5 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {chartData.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => toggle(entry.id)}
            className={`flex items-center justify-between gap-3 rounded-md px-1.5 py-1 text-left transition-colors ${
              onPlatformClick ? 'cursor-pointer hover:bg-muted/60' : ''
            } ${activeName === entry.id ? 'bg-muted' : ''}`}
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
          </button>
        ))}
      </div>
    </motion.div>
  )
})
