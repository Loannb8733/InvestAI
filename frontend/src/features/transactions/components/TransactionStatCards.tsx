import { useMemo, type ReactNode } from 'react'
import { Coins, Receipt, TrendingDown, TrendingUp, type LucideIcon } from 'lucide-react'
import SpotlightGroup from '@/components/ui/spotlight-group'
import StatCard from '@/components/ui/stat-card'
import { formatCurrency } from '@/lib/utils'
import { computeStats, EMPTY_TOTALS } from '../ledger'
import type { CurrencyTotals, Transaction } from '../types'

interface TransactionStatCardsProps {
  transactions: Transaction[]
  total: number
  filtered: boolean
}

interface CardSpec {
  field: keyof CurrencyTotals
  label: string
  tooltip?: string
  icon: LucideIcon
  lead?: string
  showExcluded: boolean
}

const CARDS: CardSpec[] = [
  { field: 'bought', label: 'Total achats', tooltip: 'Achats (BUY) uniquement — transferts, conversions et récompenses exclus.', icon: TrendingUp, showExcluded: true },
  { field: 'sold', label: 'Total ventes', tooltip: 'Ventes (SELL) uniquement — transferts, conversions et récompenses exclus.', icon: TrendingDown, showExcluded: true },
  { field: 'fees', label: 'Total frais', tooltip: 'Frais de tous les types de mouvements, cumulés par devise.', icon: Receipt, showExcluded: false },
  { field: 'netFlow', label: 'Flux net investi', icon: Coins, lead: 'hors transferts internes, conversions et récompenses', showExcluded: false },
]

const block = (text: string | null) => text && <span className="block">{text}</span>

export default function TransactionStatCards({ transactions, total, filtered }: TransactionStatCardsProps) {
  const stats = useMemo(() => computeStats(transactions), [transactions])
  const eur = stats.byCurrency['EUR'] ?? EMPTY_TOTALS
  const others = Object.keys(stats.byCurrency).filter((c) => c !== 'EUR').sort()
  const excluded =
    stats.excludedCount > 1 ? `${stats.excludedCount} transferts/rewards exclus` : stats.excludedCount === 1 ? '1 transfert/reward exclu' : null
  const partial = total > transactions.length ? `sur les ${transactions.length} chargées` : null

  const otherLines = (field: keyof CurrencyTotals) =>
    others
      .filter((c) => stats.byCurrency[c][field] !== 0)
      .map((c) => {
        const amount = stats.byCurrency[c][field]
        return (
          <span key={`${field}-${c}`} className="block">
            {amount >= 0 ? '+ ' : ''}
            {formatCurrency(amount, c)}
          </span>
        )
      })

  const hint = (card: CardSpec): ReactNode => {
    const lines = otherLines(card.field)
    const excludedLine = card.showExcluded ? excluded : null
    if (!card.lead && lines.length === 0 && !excludedLine && !partial) return undefined
    return (
      <>
        {block(card.lead ?? null)}
        {lines}
        {block(excludedLine)}
        {block(partial)}
      </>
    )
  }

  return (
    <SpotlightGroup className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {CARDS.map((card) => (
        <StatCard
          key={card.field}
          className="spot-card"
          label={`${card.label}${filtered ? ' (filtrés)' : ''}`}
          tooltip={card.tooltip}
          icon={card.icon}
          value={eur[card.field]}
          format={formatCurrency}
          hint={hint(card)}
        />
      ))}
    </SpotlightGroup>
  )
}
