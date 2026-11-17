import { AlertTriangle, Loader2 } from 'lucide-react'
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

interface ConfirmDeleteDialogProps {
  title: string
  subject: string | null
  question: string
  consequence: string
  pending: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDeleteDialog({
  title,
  subject,
  question,
  consequence,
  pending,
  onConfirm,
  onCancel,
}: ConfirmDeleteDialogProps) {
  return (
    <AlertDialog open={subject !== null} onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {subject !== null && (
              <>
                {question} <strong>{subject}</strong> ?
                <br /><br />
                <span className="text-destructive font-medium">{consequence}</span>
                <br />
                Cette action est irréversible.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <AlertDialogAction className="bg-destructive hover:bg-destructive/90" onClick={onConfirm} disabled={pending}>
            {pending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Supprimer
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
