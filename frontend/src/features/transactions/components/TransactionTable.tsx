import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import type { SortField, Transaction } from '../types'
import type { Ledger } from '../useLedger'
import TransactionRow from './TransactionRow'

interface SortableHeaderProps {
  field: SortField
  sort: Ledger['sort']
  title?: string
  children: ReactNode
}

function SortableHeader({ field, sort, title, children }: SortableHeaderProps) {
  const Arrow = sort.field !== field ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown
  return (
    <th
      scope="col"
      title={title}
      className="text-center py-3 text-sm font-medium text-muted-foreground cursor-pointer hover:text-foreground transition-colors select-none"
      onClick={() => sort.by(field)}
    >
      <div className="flex items-center justify-center gap-1">
        {children}
        <Arrow className={sort.field === field ? 'h-3 w-3' : 'h-3 w-3 opacity-30'} />
      </div>
    </th>
  )
}

const PLAIN_HEADER = 'text-center py-3 text-sm font-medium text-muted-foreground'

interface TransactionTableProps {
  ledger: Ledger
  onEdit: (tx: Transaction) => void
  onDelete: (tx: Transaction) => void
}

export default function TransactionTable({ ledger, onEdit, onDelete }: TransactionTableProps) {
  const { visible, selection, sort } = ledger
  const pageIds = visible.map((tx) => tx.id)
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b">
            <th scope="col" className="text-center py-3 w-10">
              <Checkbox
                checked={visible.length > 0 && visible.every((tx) => selection.ids.has(tx.id))}
                onCheckedChange={() => selection.togglePage(pageIds)}
                aria-label="Sélectionner toutes les transactions de la page"
              />
            </th>
            <SortableHeader field="date" sort={sort}>Date</SortableHeader>
            <SortableHeader field="type" sort={sort}>Type</SortableHeader>
            <SortableHeader field="asset" sort={sort}>Actif</SortableHeader>
            <th scope="col" className={PLAIN_HEADER}>Plateforme</th>
            <SortableHeader field="quantity" sort={sort}>Quantité</SortableHeader>
            <SortableHeader field="price" sort={sort}>Prix</SortableHeader>
            <SortableHeader field="total" sort={sort} title="Hors frais">Total</SortableHeader>
            <SortableHeader field="fee" sort={sort}>Frais</SortableHeader>
            <th scope="col" className={`${PLAIN_HEADER} w-20`}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((tx) => (
            <TransactionRow
              key={tx.id}
              tx={tx}
              selected={selection.ids.has(tx.id)}
              onToggle={selection.toggle}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
