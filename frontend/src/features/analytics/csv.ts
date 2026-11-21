import type { AnalyticsData } from './types'

const HEADERS = ['Actif', 'Type', 'Valeur (EUR)', 'Performance %', 'Poids %', 'Volatilité', 'Sharpe', 'Sortino', 'Max Drawdown', 'Rendement J']

const fixed = (value: number | null | undefined) => (value == null || isNaN(value) ? '—' : value.toFixed(2))

function escape(value: string) {
  return value.includes(',') || value.includes('"') || value.includes('\n') ? `"${value.replace(/"/g, '""')}"` : value
}

function analyticsCsv(assets: AnalyticsData['assets']) {
  const rows = assets.map((asset) => [
    escape(asset.symbol),
    escape(asset.asset_type),
    fixed(asset.current_value),
    fixed(asset.gain_loss_percent),
    fixed(asset.weight),
    fixed(asset.volatility_30d),
    fixed(asset.sharpe_ratio),
    fixed(asset.sortino_ratio),
    fixed(asset.max_drawdown),
    fixed(asset.daily_return),
  ])
  return [HEADERS.join(','), ...rows.map((row) => row.join(','))].join('\n')
}

export function downloadAnalyticsCsv(assets: AnalyticsData['assets']) {
  const blob = new Blob(['﻿' + analyticsCsv(assets)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `analyse-portefeuille-${new Date().toISOString().split('T')[0]}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
