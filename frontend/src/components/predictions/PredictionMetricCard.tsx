import React from 'react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { type DisplayThresholds, DEFAULT_DISPLAY_THRESHOLDS } from '@/types'

// ── Fear & Greed Arc Gauge ───────────────────────────────────────────

export const FearGreedGauge = React.memo(({ value, thresholds }: {
  value: number
  thresholds?: DisplayThresholds['fear_greed']
}) => {
  const clampedValue = Math.max(0, Math.min(100, value))
  const angle = Math.max(1, (clampedValue / 100) * 180)
  const radians = (angle * Math.PI) / 180
  const x = 60 - 45 * Math.cos(radians)
  const y = 55 - 45 * Math.sin(radians)

  const fg = thresholds ?? DEFAULT_DISPLAY_THRESHOLDS.fear_greed

  const getColor = (v: number) => {
    if (v >= fg.extreme_greed) return '#22c55e'
    if (v >= fg.greed) return '#84cc16'
    if (v >= fg.fear) return '#eab308'
    if (v >= fg.extreme_fear) return '#f97316'
    return '#ef4444'
  }
  const getLabel = (v: number) => {
    if (v >= fg.extreme_greed) return 'Extrême avidité'
    if (v >= fg.greed) return 'Avidité'
    if (v >= fg.fear) return 'Neutre'
    if (v >= fg.extreme_fear) return 'Peur'
    return 'Extrême peur'
  }
  const color = getColor(clampedValue)

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="85" viewBox="0 0 120 70">
        <path
          d="M 15 55 A 45 45 0 0 1 105 55"
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          className="text-muted/20"
        />
        <path
          d={`M 15 55 A 45 45 0 ${angle > 180 ? 1 : 0} 1 ${x} ${y}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
        />
        <text x="60" y="50" textAnchor="middle" fill={color} fontSize="22" fontWeight="bold">
          {Math.round(clampedValue)}
        </text>
      </svg>
      <span className="text-sm font-medium" style={{ color }}>{getLabel(clampedValue)}</span>
    </div>
  )
})
FearGreedGauge.displayName = 'FearGreedGauge'

// ── Cycle Position Gauge ─────────────────────────────────────────────

export const CycleGauge = React.memo(({ position }: { position: number }) => {
  const clampedPos = Math.max(0, Math.min(100, position))
  const angle = (clampedPos / 100) * 360
  const radians = ((angle - 90) * Math.PI) / 180
  const cx = 60, cy = 60, r = 45
  const nx = cx + r * Math.cos(radians)
  const ny = cy + r * Math.sin(radians)

  const getPhase = (pos: number): { label: string; color: string } => {
    if (pos < 15) return { label: 'Creux', color: '#3b82f6' }
    if (pos < 40) return { label: 'Accumulation', color: '#06b6d4' }
    if (pos < 65) return { label: 'Expansion', color: '#22c55e' }
    if (pos < 85) return { label: 'Distribution', color: '#f59e0b' }
    return { label: 'Euphorie', color: '#ef4444' }
  }
  const phase = getPhase(clampedPos)

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="140" viewBox="0 0 120 120">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/20" />
        {[
          { start: -90, end: -36, c: '#3b82f6' },
          { start: -36, end: 54, c: '#06b6d4' },
          { start: 54, end: 144, c: '#22c55e' },
          { start: 144, end: 216, c: '#f59e0b' },
          { start: 216, end: 270, c: '#ef4444' },
        ].map(({ start, end, c }, i) => {
          const s = (start * Math.PI) / 180
          const e = (end * Math.PI) / 180
          const x1 = cx + r * Math.cos(s)
          const y1 = cy + r * Math.sin(s)
          const x2 = cx + r * Math.cos(e)
          const y2 = cy + r * Math.sin(e)
          const largeArc = (end - start) > 180 ? 1 : 0
          return (
            <path
              key={i}
              d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
              fill="none"
              stroke={c}
              strokeWidth="8"
              opacity={0.2}
            />
          )
        })}
        <circle cx={nx} cy={ny} r="6" fill={phase.color} stroke="white" strokeWidth="2" />
        <text x={cx} y={cy - 4} textAnchor="middle" fill={phase.color} fontSize="14" fontWeight="bold">
          {phase.label}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill="currentColor" fontSize="10" className="fill-muted-foreground">
          Position: {clampedPos}
        </text>
        <text x={cx} y="10" textAnchor="middle" fontSize="7" className="fill-muted-foreground">Creux</text>
        <text x="112" y={cy + 3} textAnchor="start" fontSize="7" className="fill-muted-foreground">Expansion</text>
        <text x={cx} y="116" textAnchor="middle" fontSize="7" className="fill-muted-foreground">Distribution</text>
        <text x="2" y={cy + 3} textAnchor="start" fontSize="7" className="fill-muted-foreground">Euphorie</text>
      </svg>
    </div>
  )
})
CycleGauge.displayName = 'CycleGauge'

// ── Reliability Score ────────────────────────────────────────────────

export interface ReliabilityScoreProps {
  reliabilityScore: number
  skillScore: number
  hitRate: number
  hitRateSignificant: boolean
  hitRateN: number
  modelConfidence: string
}

export const ReliabilityScore = React.memo(({
  reliabilityScore, skillScore, hitRate, hitRateSignificant, hitRateN, modelConfidence,
}: ReliabilityScoreProps) => {
  const score = Math.round(reliabilityScore)
  const color = score >= 60 ? 'bg-green-500' : score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = score >= 60 ? 'text-green-500' : score >= 40 ? 'text-yellow-500' : 'text-red-500'
  const label = modelConfidence === 'useful' ? 'Utile' : modelConfidence === 'uncertain' ? 'Incertain' : 'Non fiable'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 cursor-help">
            <div className="w-14 h-2 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
            </div>
            <span className={`text-xs font-bold ${textColor}`}>{score}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs font-medium mb-1">{label}</p>
          <p className="text-xs">Skill: {skillScore.toFixed(0)}% · Direction: {hitRate.toFixed(0)}% ({hitRateN} tests{hitRateSignificant ? ', significatif' : ', non significatif'})</p>
          <p className="text-xs text-muted-foreground mt-1">Mesure si le modèle fait mieux qu'une prédiction naïve (prix inchangé)</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})
ReliabilityScore.displayName = 'ReliabilityScore'

// ── Variation Bar ────────────────────────────────────────────────────

export const VariationBar = React.memo(({ percent }: { percent: number }) => {
  const clamped = Math.max(-20, Math.min(20, percent))
  const width = Math.abs(clamped) / 20 * 50
  const isPositive = percent >= 0

  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 rounded-full bg-muted relative overflow-hidden">
        <div
          className={`absolute h-full rounded-full ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
          style={{
            width: `${width}%`,
            left: isPositive ? '50%' : `${50 - width}%`,
          }}
        />
        <div className="absolute left-1/2 top-0 w-px h-full bg-muted-foreground/30" />
      </div>
      <span className={`text-sm font-bold tabular-nums ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
        {isPositive ? '+' : ''}{percent.toFixed(1)}%
      </span>
    </div>
  )
})
VariationBar.displayName = 'VariationBar'
