import { useState } from 'react'
import { useToast } from '@/hooks/use-toast'
import { counted } from '@/lib/utils'
import { generateCSV, saveFile, today } from './format'
import { fetchTransactionsCsv } from './hooks'
import type { Ledger } from './useLedger'
import type { Transaction } from './types'

const csvBlob = (transactions: Transaction[]) => new Blob([generateCSV(transactions)], { type: 'text/csv;charset=utf-8;' })

export function useExports(ledger: Ledger) {
  const { toast } = useToast()
  const [exportingAll, setExportingAll] = useState(false)
  const portfolioId = ledger.filters.server.portfolio_id

  const exportAll = async () => {
    if (exportingAll) return
    setExportingAll(true)
    try {
      saveFile(await fetchTransactionsCsv(portfolioId), `transactions_all_${today()}.csv`)
      toast({
        title: 'Export complet téléchargé',
        description: portfolioId
          ? 'Toutes les transactions du portefeuille ont été exportées.'
          : 'Toutes les transactions ont été exportées.',
      })
    } catch {
      toast({ title: "Erreur lors de l'export", variant: 'destructive' })
    } finally {
      setExportingAll(false)
    }
  }

  const exportFiltered = () => {
    if (ledger.loaded.length === 0) {
      toast({ title: 'Aucune transaction à exporter', variant: 'destructive' })
      return
    }
    saveFile(csvBlob(ledger.loaded), `transactions_filtered_${today()}.csv`)
    toast({ title: counted(ledger.loaded.length, 'transaction exportée', 'transactions exportées') })
  }

  const exportSelected = () => {
    if (ledger.selection.ids.size === 0) {
      toast({ title: 'Aucune transaction sélectionnée', variant: 'destructive' })
      return
    }
    const selected = ledger.sorted.filter((tx) => ledger.selection.ids.has(tx.id))
    saveFile(csvBlob(selected), `transactions_selected_${today()}.csv`)
    toast({ title: counted(selected.length, 'transaction exportée', 'transactions exportées') })
  }

  return { exportingAll, exportAll, exportFiltered, exportSelected }
}

export type Exports = ReturnType<typeof useExports>
