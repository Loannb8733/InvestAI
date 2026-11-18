import { Badge } from '@/components/ui/badge'
import EmptyState from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCurrency } from '@/lib/utils'
import { formatDetailQuantity } from '../format'
import { TX_LIMIT, useAssetTransactions } from '../hooks'
import type { AssetTransaction, Position } from '../types'

const txTypeLabels: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Reward',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
  dividend: 'Dividende',
  interest: 'Intérêts',
  fee: 'Frais',
  staking: 'Staking',
  unstaking: 'Unstaking',
}

const txBadgeVariant = (type: string): 'gain' | 'loss' | 'warning' | 'secondary' => {
  switch (type) {
    case 'buy':
    case 'conversion_in':
    case 'dividend':
      return 'gain'
    case 'sell':
    case 'fee':
      return 'loss'
    case 'transfer_out':
    case 'conversion_out':
      return 'warning'
    default:
      return 'secondary'
  }
}

const formatTxDate = (tx: AssetTransaction) =>
  new Date(tx.executed_at || tx.created_at).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })

const HEADERS = [
  { label: 'Date', align: 'text-left' },
  { label: 'Type', align: 'text-left' },
  { label: 'Quantité', align: 'text-right' },
  { label: 'Prix', align: 'text-right' },
  { label: 'Total', align: 'text-right' },
]

function TransactionsTable({ transactions }: { transactions: AssetTransaction[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40">
            {HEADERS.map(({ label, align }) => (
              <th key={label} scope="col" className={`px-3 py-2 ${align} font-medium text-muted-foreground`}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.id} className="border-b last:border-0">
              <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{formatTxDate(tx)}</td>
              <td className="px-3 py-2">
                <Badge variant={txBadgeVariant(tx.transaction_type)}>
                  {txTypeLabels[tx.transaction_type] || tx.transaction_type}
                </Badge>
              </td>
              <td className="px-3 py-2 text-right">{formatDetailQuantity(tx.quantity)}</td>
              <td className="px-3 py-2 text-right text-muted-foreground">{formatCurrency(tx.price, tx.currency)}</td>
              <td className="px-3 py-2 text-right font-medium">{formatCurrency(tx.quantity * tx.price, tx.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AssetTransactions({ assets, open }: { assets: Position[]; open: boolean }) {
  const { loading, failed, transactions } = useAssetTransactions(assets, open)
  return (
    <section aria-label="Transactions de l'actif">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">Transactions</h3>
        {!loading && transactions.length >= TX_LIMIT && (
          <span className="text-xs text-muted-foreground">
            {TX_LIMIT} plus récentes
          </span>
        )}
      </div>
      {loading ? (
        <div className="space-y-2" aria-hidden>
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : failed ? (
        <EmptyState variant="error" title="Impossible de charger les transactions" description="Réessayez en rouvrant le panneau." />
      ) : transactions.length === 0 ? (
        <EmptyState title="Aucune transaction" description="Cet actif n'a pas encore de transaction enregistrée." />
      ) : (
        <TransactionsTable transactions={transactions} />
      )}
    </section>
  )
}
