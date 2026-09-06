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
import type { APIKey } from '@/types/exchanges'

/**
 * Confirmation de suppression d'une connexion à une plateforme.
 *
 * Le texte insiste sur ce qui **ne** disparaît pas : supprimer une clé retire
 * l'accès à la plateforme, pas les transactions déjà importées. Sans cette
 * précision, l'utilisateur peut croire qu'il efface son historique.
 */
interface DeleteConnectionDialogProps {
  cible: APIKey | null
  nomExchange: (exchangeId: string) => string
  onConfirmer: () => void
  onFermer: () => void
}

export default function DeleteConnectionDialog({
  cible,
  nomExchange,
  onConfirmer,
  onFermer,
}: DeleteConnectionDialogProps) {
  return (
    <AlertDialog open={!!cible} onOpenChange={onFermer}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Supprimer cette connexion ?</AlertDialogTitle>
          <AlertDialogDescription>
            Vous êtes sur le point de supprimer la connexion à{' '}
            <strong>{cible && nomExchange(cible.exchange)}</strong>
            {cible?.label && <> ({cible.label})</>}.
            <br />
            <br />
            Vos données importées (transactions, actifs) resteront dans l'application. Vous pourrez
            reconnecter cet exchange à tout moment.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirmer}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Supprimer
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
