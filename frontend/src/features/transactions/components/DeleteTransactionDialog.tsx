import { AlertTriangle } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { formatQuantity } from '../format'
import { useDeleteTransaction } from '../hooks'
import { typeLabel } from '../labels'
import type { Transaction } from '../types'
import DeleteAction from './DeleteAction'

interface DeleteTransactionDialogProps {
  transaction: Transaction | null
  onClose: () => void
}

export default function DeleteTransactionDialog({ transaction, onClose }: DeleteTransactionDialogProps) {
  const remove = useDeleteTransaction(onClose)
  return (
    <AlertDialog open={transaction !== null} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Supprimer cette transaction ?
          </AlertDialogTitle>
          <AlertDialogDescription>
            {transaction && (
              <span>
                Voulez-vous vraiment supprimer la transaction <strong>{typeLabel(transaction.transaction_type)}</strong> de{' '}
                <strong>
                  {formatQuantity(transaction.quantity)} {transaction.asset_symbol}
                </strong>{' '}
                ?
                <br />
                Cette action est irréversible.
              </span>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <DeleteAction
            pending={remove.isPending}
            label="Supprimer"
            onConfirm={() => transaction && remove.mutate(transaction.id)}
          />
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
