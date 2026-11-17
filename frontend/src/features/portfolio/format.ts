export const formatNumber = (value: number, digits: number) =>
  value.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const formatQuantity = (quantity: number) => formatNumber(quantity, quantity < 1 ? 8 : 2)

export const formatSignedPercent = (value: number, digits = 1) => `${value >= 0 ? '+' : ''}${formatNumber(value, digits)} %`

export const formatDetailQuantity = (q: number) =>
  q.toLocaleString('fr-FR', { maximumFractionDigits: Math.abs(q) < 1 ? 8 : 4 })

export const arrow = (value: number) => (value >= 0 ? '▲' : '▼')

export const gainClass = (value: number) => (value >= 0 ? 'text-gain' : 'text-loss')

export function formatHoldingPeriod(first: string | null, last: string | null) {
  if (!first || !last) return '—'
  const firstDate = new Date(first)
  const lastDate = new Date(last)
  if (Number.isNaN(firstDate.getTime()) || Number.isNaN(lastDate.getTime())) return '—'
  return `${firstDate.toLocaleDateString('fr-FR')} → ${lastDate.toLocaleDateString('fr-FR')}`
}

export function riskClass(weight: number) {
  if (weight > 30) return 'bg-loss/10 text-loss'
  if (weight > 15) return 'bg-warning/10 text-warning'
  return 'bg-gain/10 text-gain'
}
