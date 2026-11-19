import { Wallet } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatQuantity } from '../format'

interface ImpactSummaryProps {
  type: string
  symbol: string
  held: number
  quantity: number
  total: number
  format: (value: number) => string
}

const formatHolding = (value: number, symbol: string) => `${formatQuantity(value)} ${symbol}`

export default function ImpactSummary({ type, symbol, held, quantity, total, format }: ImpactSummaryProps) {
  const neutral = ['staking', 'unstaking'].includes(type)
  const free = ['staking_reward', 'airdrop'].includes(type)
  const inbound = ['buy', 'transfer_in', 'staking_reward', 'airdrop', 'conversion_in'].includes(type)
  const after = neutral ? held : inbound ? held + quantity : held - quantity
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-3 space-y-2">
      <div className="flex items-center gap-1.5">
        <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
        <p className="text-xs font-medium text-muted-foreground">Résumé de l'impact</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-0.5">
          <p className="text-[10px] text-muted-foreground">Nouveau solde</p>
          <p className="text-sm font-semibold">{formatHolding(isNaN(after) ? 0 : after, symbol)}</p>
        </div>
        {total > 0 && (
          <div className="space-y-0.5 text-right">
            <p className="text-[10px] text-muted-foreground">{free ? 'Valeur estimée' : inbound ? 'Impact Cash' : 'Montant récupéré'}</p>
            <p className={cn('text-sm font-semibold', free ? 'text-muted-foreground' : inbound ? 'text-loss' : 'text-gain')}>
              {free ? '≈ ' : inbound ? '-' : '+'}
              {format(total)}
            </p>
          </div>
        )}
      </div>
      {!inbound && after < 0 && <p className="text-xs text-destructive font-medium">Attention : solde négatif après transaction</p>}
    </div>
  )
}
