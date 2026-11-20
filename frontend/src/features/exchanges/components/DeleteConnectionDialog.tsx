import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type { ApiKey } from '../types'

interface DeleteConnectionDialogProps {
  target: ApiKey | null
  exchangeName: (exchangeId: string) => string
  onConfirm: () => void
  onClose: () => void
}

export default function DeleteConnectionDialog({ target, exchangeName, onConfirm, onClose }: DeleteConnectionDialogProps) {
  return (
    <AlertDialog open={!!target} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Supprimer cette connexion ?</AlertDialogTitle>
          <AlertDialogDescription>
            Vous êtes sur le point de supprimer la connexion à{' '}
            <strong>{target && exchangeName(target.exchange)}</strong>
            {target?.label && <> ({target.label})</>}.
            <br />
            <br />
            Vos données importées (transactions, actifs) resteront dans l'application. Vous pourrez
            reconnecter cet exchange à tout moment.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Supprimer
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
