import { ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'
import type { DeepPartial, ChartOptions } from 'lightweight-charts'
import { oklchVar } from '@/lib/oklch'

export interface ResolvedChartTheme {
  options: DeepPartial<ChartOptions>
  area: {
    lineColor: string
    topColor: string
    bottomColor: string
  }
  invested: {
    color: string
  }
  markerBorder: string
}

export function resolveChartTheme(accent = '--chart-1'): ResolvedChartTheme {
  const text = oklchVar('--muted-foreground')
  const grid = oklchVar('--border', 0.6)
  const border = oklchVar('--border')
  const line = oklchVar(accent)

  return {
    options: {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: text,
        fontFamily: "'Public Sans', system-ui, -apple-system, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: grid, style: LineStyle.Dotted },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.15, bottom: 0.08 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: false,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: {
          color: border,
          width: 1,
          style: LineStyle.Dashed,
          labelVisible: false,
        },
        horzLine: {
          color: border,
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: oklchVar('--card'),
        },
      },
      handleScale: false,
      handleScroll: false,
    },
    area: {
      lineColor: line,
      topColor: oklchVar(accent, 0.22),
      bottomColor: oklchVar(accent, 0),
    },
    invested: {
      color: oklchVar('--muted-foreground', 0.9),
    },
    markerBorder: oklchVar('--background'),
  }
}
