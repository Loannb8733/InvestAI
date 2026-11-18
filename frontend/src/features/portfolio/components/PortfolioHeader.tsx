import { Download, Plus, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { saveFile } from '@/features/transactions/format'
import { fetchTransactionsCsv } from '@/features/transactions/hooks'

interface PortfolioHeaderProps {
  portfolioId: string | null
  onImport: () => void
  onAddPortfolio: () => void
}

export default function PortfolioHeader({ portfolioId, onImport, onAddPortfolio }: PortfolioHeaderProps) {
  const { toast } = useToast()

  const exportCsv = async () => {
    try {
      saveFile(await fetchTransactionsCsv(portfolioId || undefined), 'transactions_export.csv')
      toast({ title: 'Export réussi', description: 'Le fichier CSV a été téléchargé.' })
    } catch {
      toast({ variant: 'destructive', title: 'Erreur', description: "Impossible d'exporter les transactions." })
    }
  }

  return (
    <div className="flex items-center justify-between">
      <div>
        <h2 className="text-3xl font-serif font-medium">Portefeuille</h2>
        <p className="text-sm text-muted-foreground mt-1">Le détail de ce que tu possèdes, ligne par ligne.</p>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={onImport}>
          <Upload className="h-4 w-4 mr-2" />
          Importer CSV
        </Button>
        <Button variant="outline" onClick={exportCsv}>
          <Download className="h-4 w-4 mr-2" />
          Exporter CSV
        </Button>
        <Button onClick={onAddPortfolio}>
          <Plus className="h-4 w-4 mr-2" />
          Nouveau portefeuille
        </Button>
      </div>
    </div>
  )
}
