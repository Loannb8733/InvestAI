export function formatBalance(amount: number): string {
  if (amount === 0) return '0'
  if (amount < 0.00001) return amount.toExponential(2)
  if (amount < 1) return amount.toFixed(6)
  if (amount < 1000) return amount.toFixed(4)
  return amount.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}

export interface Freshness {
  label: string
  className: string
}

export function syncFreshness(dateString: string): Freshness | null {
  const ts = new Date(dateString).getTime()
  if (Number.isNaN(ts)) return null
  const diffMs = Date.now() - ts
  if (diffMs < 0) return null
  const hours = Math.floor(diffMs / 3_600_000)
  const days = Math.floor(hours / 24)
  const label = hours < 1 ? "il y a moins d'1 h" : hours < 24 ? `il y a ${hours} h` : `il y a ${days} j`
  const className =
    hours < 24
      ? 'text-gain border-gain/30 bg-gain/10'
      : days <= 3
        ? 'text-warning border-warning/30 bg-warning/10'
        : 'text-loss border-loss/30 bg-loss/10'
  return { label, className }
}

export function shortError(error: string): string {
  return error.length > 120 ? `${error.slice(0, 120)}…` : error
}

export function totalMissingEur(gaps: Array<{ missing_eur: number }>): number {
  return gaps.reduce((sum, gap) => sum + gap.missing_eur, 0)
}
