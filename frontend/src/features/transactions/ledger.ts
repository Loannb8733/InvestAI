import { EXCLUDED_FROM_FLOWS, platformLabel, typeLabel } from './labels'
import type { Choice, CurrencyTotals, SortDirection, SortField, Transaction, TransactionStats } from './types'

export const totalOf = (tx: Transaction) => tx.quantity * tx.price

const executedAt = (tx: Transaction) => new Date(tx.executed_at || tx.created_at).getTime()

const COMPARATORS: Record<SortField, (a: Transaction, b: Transaction) => number> = {
  date: (a, b) => executedAt(a) - executedAt(b),
  type: (a, b) => typeLabel(a.transaction_type).localeCompare(typeLabel(b.transaction_type)),
  asset: (a, b) => (a.asset_symbol || '').localeCompare(b.asset_symbol || ''),
  quantity: (a, b) => a.quantity - b.quantity,
  price: (a, b) => a.price - b.price,
  total: (a, b) => totalOf(a) - totalOf(b),
  fee: (a, b) => (a.fee || 0) - (b.fee || 0),
}

export function sortTransactions(list: Transaction[], field: SortField, direction: SortDirection) {
  const compare = COMPARATORS[field]
  return [...list].sort((a, b) => (direction === 'asc' ? compare(a, b) : -compare(a, b)))
}

export const EMPTY_TOTALS: CurrencyTotals = { bought: 0, sold: 0, fees: 0, netFlow: 0 }

export function computeStats(list: Transaction[]): TransactionStats {
  const byCurrency: Record<string, CurrencyTotals> = {}
  let excludedCount = 0
  for (const tx of list) {
    const entry = (byCurrency[tx.currency || 'EUR'] ??= { ...EMPTY_TOTALS })
    const total = (Number(tx.quantity) || 0) * (Number(tx.price) || 0)
    entry.fees += Number(tx.fee) || 0
    if (tx.transaction_type === 'buy') entry.bought += total
    else if (tx.transaction_type === 'sell') entry.sold += total
    else if (EXCLUDED_FROM_FLOWS.includes(tx.transaction_type)) excludedCount++
  }
  for (const entry of Object.values(byCurrency)) entry.netFlow = entry.bought - entry.sold
  return { byCurrency, excludedCount }
}

function countBy(list: Transaction[], key: (tx: Transaction) => string | null, selected: string): Choice[] {
  const counts = new Map<string, number>()
  for (const tx of list) {
    const value = key(tx)
    if (value) counts.set(value, (counts.get(value) || 0) + 1)
  }
  const choices = [...counts.entries()].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count)
  if (selected !== 'all' && !counts.has(selected)) choices.push({ value: selected, count: 0 })
  return choices
}

export const assetChoices = (list: Transaction[], selected: string) => countBy(list, (tx) => tx.asset_symbol, selected)

export const platformChoices = (list: Transaction[], selected: string) =>
  countBy(list, (tx) => platformLabel(tx.exchange), selected)

export function pageNumbers(current: number, total: number): number[] {
  const length = Math.min(5, total)
  const first = total <= 5 || current <= 3 ? 1 : current >= total - 2 ? total - 4 : current - 2
  return Array.from({ length }, (_, i) => first + i)
}

export const acceptsTransactions = (portfolio: { kind?: string | null }) => portfolio.kind !== 'crowdfunding'
