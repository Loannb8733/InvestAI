import { AlertTriangle, Trash2 } from 'lucide-react'
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { counted } from '../format'
import { useDeleteAll } from '../hooks'
import DeleteAction from './DeleteAction'

interface DangerZoneProps {
  portfolioId: string | undefined
  count: number
}

export default function DangerZone({ portfolioId, count }: DangerZoneProps) {
  const removeAll = useDeleteAll(portfolioId)
  return (
    <Card elevation="raised" className="border-destructive/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-destructive flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4" />
          Zone dangereuse
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-sm">Supprimer toutes les transactions</p>
            <p className="text-xs text-muted-foreground">Supprime {counted(count, 'transaction', 'transactions')} et remet les quantités à zéro.</p>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="sm">
                <Trash2 className="h-4 w-4 mr-2" />
                Tout supprimer
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-destructive" />
                  Supprimer toutes les transactions ?
                </AlertDialogTitle>
                <AlertDialogDescription>
                  Cette action est irréversible.{' '}
                  {portfolioId
                    ? `Les transactions du portefeuille sélectionné (${count}) seront`
                    : `Toutes vos transactions (${count}) seront`}{' '}
                  définitivement supprimées et les quantités des actifs concernés seront remises à zéro.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Annuler</AlertDialogCancel>
                <DeleteAction pending={removeAll.isPending} label="Supprimer tout" onConfirm={() => removeAll.mutate(undefined)} />
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  )
}
