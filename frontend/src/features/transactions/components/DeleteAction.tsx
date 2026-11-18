import { Loader2 } from 'lucide-react'
import { AlertDialogAction } from '@/components/ui/alert-dialog'

interface DeleteActionProps {
  pending: boolean
  label: string
  onConfirm: () => void
}

export default function DeleteAction({ pending, label, onConfirm }: DeleteActionProps) {
  return (
    <AlertDialogAction
      onClick={onConfirm}
      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
      disabled={pending}
    >
      {pending ? (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          Suppression...
        </>
      ) : (
        label
      )}
    </AlertDialogAction>
  )
}
