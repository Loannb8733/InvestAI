import { Banknote } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import { formatNumber } from '../format'
import { useMoney } from '../hooks'
import type { PortfolioPerformance } from '../types'

interface CashCardsProps {
  performance: PortfolioPerformance | undefined
  cashBalances: Record<string, number>
  onOpenCashBalance: () => void
}

export default function CashCards({ performance, cashBalances, onOpenCashBalance }: CashCardsProps) {
  const money = useMoney()
  const totalCash = (performance?.cash_from_balances ?? 0) + (performance?.cash_from_fiat ?? 0)
  const cashEntries = Object.entries(cashBalances)
  const fiatEntries = performance?.fiat_assets ?? []
  const stablecoins = performance?.stablecoins.filter((sc) => sc.value >= 0.01) ?? []

  return (
    <div className="grid grid-cols-2 gap-4 mb-4">
      <Card elevation="interactive" className="cursor-pointer hover:bg-muted/50 transition-colors" onClick={onOpenCashBalance}>
        <CardContent className="py-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-gain/20 flex items-center justify-center shrink-0">
              <Banknote className="h-5 w-5 text-gain" />
            </div>
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">Cash disponible</p>
              <p className="text-xl font-bold">{money(totalCash)}</p>
              {(cashEntries.length > 0 || fiatEntries.length > 0) && (
                <div className="text-xs text-muted-foreground mt-1">
                  {cashEntries.map(([ex, amt]) => (
                    <span key={ex} className="mr-2">{ex}: {formatCurrency(amt)}</span>
                  ))}
                  {fiatEntries.map((f) => (
                    <span key={f.id} className="mr-2">{f.symbol}: {money(f.value)}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card elevation="raised">
        <CardContent className="py-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
              <span className="text-accent font-bold text-sm">$</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">Stablecoins</p>
              <p className="text-xl font-bold">{money(performance?.cash_from_stablecoins || 0)}</p>
              {stablecoins.length > 0 && (
                <div className="text-xs text-muted-foreground mt-1">
                  {stablecoins.map((sc) => (
                    <span key={sc.id} className="mr-2">{sc.symbol}: {formatNumber(sc.quantity, 2)}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
