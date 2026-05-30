import { useMemo } from 'react'
import { useTheme } from '@/components/theme-provider'
import { oklchVar } from '@/lib/oklch'

const FONT = "'Public Sans', system-ui, -apple-system, sans-serif"

export interface NivoFluxTheme {
  /** Nivo `theme` prop — axes, grid, labels, tooltip, crosshair. */
  theme: Record<string, unknown>
  /** Ordered categorical series palette (chart-1..5), resolved to rgb. */
  palette: string[]
  /** Resolve any OKLCH token to an rgb()/rgba() string. */
  color: (name: string, alpha?: number) => string
}

/**
 * Flux design tokens for Nivo charts. Colors are pre-resolved to rgb() because
 * Nivo's internal d3-color math cannot parse oklch(). Recomputes on theme flip.
 */
export function useNivoTheme(): NivoFluxTheme {
  const { theme: mode } = useTheme()

  return useMemo<NivoFluxTheme>(() => {
    const color = (name: string, alpha?: number) => oklchVar(name, alpha)

    const text = color('--muted-foreground')
    const border = color('--border')
    const grid = color('--border', 0.55)

    return {
      color,
      palette: [
        color('--chart-1'),
        color('--chart-2'),
        color('--chart-3'),
        color('--chart-4'),
        color('--chart-5'),
      ],
      theme: {
        background: 'transparent',
        text: { fontFamily: FONT, fontSize: 11, fill: text },
        axis: {
          domain: { line: { stroke: 'transparent', strokeWidth: 0 } },
          ticks: {
            line: { stroke: 'transparent', strokeWidth: 0 },
            text: { fontFamily: FONT, fontSize: 11, fill: text },
          },
          legend: { text: { fontFamily: FONT, fontSize: 11, fill: text } },
        },
        grid: {
          line: { stroke: grid, strokeWidth: 1, strokeDasharray: '2 4' },
        },
        legends: {
          text: { fontFamily: FONT, fontSize: 12, fill: text },
        },
        tooltip: {
          container: {
            background: color('--popover'),
            color: color('--popover-foreground'),
            fontFamily: FONT,
            fontSize: 12,
            borderRadius: 10,
            border: `1px solid ${border}`,
            boxShadow: '0 8px 30px -8px rgba(0,0,0,0.45)',
            padding: '8px 12px',
          },
        },
        crosshair: {
          line: {
            stroke: border,
            strokeWidth: 1,
            strokeOpacity: 1,
            strokeDasharray: '4 4',
          },
        },
      },
    }
    // mode is the reactive trigger: dark/light flip re-reads CSS vars.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])
}
