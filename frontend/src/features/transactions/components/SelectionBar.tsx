import { AlertTriangle, Download, Trash2 } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useDeleteSelected } from '../hooks'
import DeleteAction from './DeleteAction'

interface SelectionBarProps {
  ids: Set<string>
  onExport: () => void
  onClear: () => void
}

export default function SelectionBar({ ids, onExport, onClear }: SelectionBarProps) {
  const removeSelected = useDeleteSelected(onClear)
  const plural = ids.size > 1 ? 's' : ''
  return (
    <div className="flex items-center gap-4 p-3 bg-primary/10 rounded-lg">
      <span className="text-sm font-medium">
        {ids.size} sélectionnée{plural}
      </span>
      <Button variant="outline" size="sm" onClick={onExport}>
        <Download className="h-4 w-4 mr-1" />
        Exporter
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm">
            <Trash2 className="h-4 w-4 mr-1" />
            Supprimer
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer {ids.size} transaction{plural} ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Cette action est irréversible. Les transactions sélectionnées seront définitivement supprimées.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <DeleteAction
              pending={removeSelected.isPending}
              label="Supprimer"
              onConfirm={() => removeSelected.mutate(Array.from(ids))}
            />
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <Button variant="ghost" size="sm" onClick={onClear}>
        Désélectionner
      </Button>
    </div>
  )
}
