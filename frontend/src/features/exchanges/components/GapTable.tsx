import { formatCurrency, formatQuantity } from '@/lib/utils'
import type { BalanceGap } from '../types'

const SOURCE_LABELS: Record<BalanceGap['source_hint'], string> = {
  earn_pending: 'Intérêts Earn',
  airdrop: 'Airdrop',
  unknown: 'Inconnue',
}

export default function GapTable({ gaps }: { gaps: BalanceGap[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">Actif</th>
            <th className="px-3 py-2 font-medium">Exchange</th>
            <th className="px-3 py-2 font-medium text-right">Écart de quantité</th>
            <th className="px-3 py-2 font-medium text-right">Valorisation estimée</th>
            <th className="px-3 py-2 font-medium">Origine probable</th>
          </tr>
        </thead>
        <tbody>
          {gaps.map((gap) => (
            <tr key={`${gap.asset_id}-${gap.exchange}`} className="border-b last:border-b-0">
              <td className="px-3 py-2 font-medium">{gap.symbol}</td>
              <td className="px-3 py-2 text-muted-foreground">{gap.exchange}</td>
              <td className="px-3 py-2 text-right font-mono">+{formatQuantity(gap.missing_qty)}</td>
              <td className="px-3 py-2 text-right font-mono">{formatCurrency(gap.missing_eur)}</td>
              <td className="px-3 py-2 text-muted-foreground">{SOURCE_LABELS[gap.source_hint] ?? 'Inconnue'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
