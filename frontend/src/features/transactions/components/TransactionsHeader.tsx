import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Plus, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { queryKeys } from '@/lib/queryKeys'
import AddTransactionForm from './AddTransactionForm'
import ImportCSVForm from './ImportCSVForm'

interface TransactionsHeaderProps {
  portfolioId: string | undefined
  adding: boolean
  onAddingChange: (open: boolean) => void
  exportMenu: ReactNode
}

export default function TransactionsHeader({ portfolioId, adding, onAddingChange, exportMenu }: TransactionsHeaderProps) {
  const queryClient = useQueryClient()
  const [importing, setImporting] = useState(false)
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.transactions.all })

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 className="text-3xl font-serif font-medium">Transactions</h2>
        <p className="text-sm text-muted-foreground mt-1">Chaque mouvement qui a façonné ton patrimoine.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {exportMenu}
        <Dialog open={importing} onOpenChange={setImporting}>
          <DialogTrigger asChild>
            <Button variant="outline">
              <Upload className="h-4 w-4 mr-2" />
              <span className="hidden sm:inline">Importer</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Importer des transactions</DialogTitle>
              <DialogDescription>Importez vos transactions depuis un fichier CSV</DialogDescription>
            </DialogHeader>
            <ImportCSVForm
              portfolioId={portfolioId}
              onSuccess={() => {
                setImporting(false)
                refresh()
              }}
            />
          </DialogContent>
        </Dialog>
        <Dialog open={adding} onOpenChange={onAddingChange}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              <span className="hidden sm:inline">Nouvelle</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Ajouter une transaction</DialogTitle>
              <DialogDescription>Enregistrez une nouvelle transaction</DialogDescription>
            </DialogHeader>
            <AddTransactionForm
              onSuccess={() => {
                onAddingChange(false)
                refresh()
                queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
              }}
            />
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
