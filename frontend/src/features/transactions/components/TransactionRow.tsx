import { ArrowDownRight, ArrowLeftRight, ArrowUpRight, MoreVertical, Pencil, Shield, Trash2 } from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { isColdWallet } from '@/lib/platforms'
import { formatCurrency, formatDateTime, formatQuantity } from '@/lib/utils'
import { CONVERSION_TYPES, INBOUND_TYPES, platformLabel, typeColor, typeLabel } from '../labels'
import { totalOf } from '../ledger'
import type { Transaction } from '../types'

interface TransactionRowProps {
  tx: Transaction
  selected: boolean
  onToggle: (id: string) => void
  onEdit: (tx: Transaction) => void
  onDelete: (tx: Transaction) => void
}

function TypeIcon({ type }: { type: string }) {
  const Icon = CONVERSION_TYPES.includes(type) ? ArrowLeftRight : INBOUND_TYPES.includes(type) ? ArrowDownRight : ArrowUpRight
  return <Icon className={`h-4 w-4 ${typeColor(type)}`} />
}

export default function TransactionRow({ tx, selected, onToggle, onEdit, onDelete }: TransactionRowProps) {
  const date = formatDateTime(tx.executed_at || tx.created_at)
  const cold = !!tx.exchange && isColdWallet(tx.exchange)
  return (
    <tr className="border-b last:border-0 hover:bg-muted/50">
      <td className="text-center py-3">
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggle(tx.id)}
          aria-label={`Sélectionner ${typeLabel(tx.transaction_type)} ${tx.asset_symbol ?? ''} du ${date}`}
        />
      </td>
      <td className="py-3 text-sm text-center whitespace-nowrap">{date}</td>
      <td className="py-3 text-center">
        <div className="flex items-center justify-center gap-1">
          <TypeIcon type={tx.transaction_type} />
          <span className={`text-sm font-medium ${typeColor(tx.transaction_type)}`}>{typeLabel(tx.transaction_type)}</span>
        </div>
      </td>
      <td className="py-3 text-center">
        <div className="flex items-center justify-center gap-2">
          <AssetIconCompact symbol={tx.asset_symbol || '?'} name={tx.asset_name || undefined} assetType={tx.asset_type} size={28} />
        </div>
      </td>
      <td className="py-3 text-center">
        <span className={`text-xs px-2 py-1 rounded inline-flex items-center gap-1 ${cold ? 'bg-accent/10 text-accent' : 'bg-muted'}`}>
          {cold && <Shield className="h-3 w-3" />}
          {platformLabel(tx.exchange)}
        </span>
      </td>
      <td className="text-center py-3 font-mono text-sm">{formatQuantity(tx.quantity)}</td>
      <td className="text-center py-3 text-sm">{formatCurrency(tx.price, tx.currency)}</td>
      <td className="text-center py-3 font-medium text-sm">{formatCurrency(totalOf(tx), tx.currency)}</td>
      <td className="text-center py-3 text-muted-foreground text-sm">
        {tx.fee && Number(tx.fee) > 0 ? formatCurrency(Number(tx.fee), tx.currency) : '-'}
      </td>
      <td className="text-center py-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 tap-target" aria-label="Actions sur la transaction">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(tx)}>
              <Pencil className="h-4 w-4 mr-2" />
              Modifier
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => onDelete(tx)} className="text-destructive focus:text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              Supprimer
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  )
}
