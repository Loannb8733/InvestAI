import { useState } from 'react'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import QueryErrorState from '@/components/ui/query-error-state'
import DangerZone from '@/features/transactions/components/DangerZone'
import DeleteTransactionDialog from '@/features/transactions/components/DeleteTransactionDialog'
import EditTransactionForm from '@/features/transactions/components/EditTransactionForm'
import ExportMenu from '@/features/transactions/components/ExportMenu'
import LedgerCard from '@/features/transactions/components/LedgerCard'
import TransactionsHeader from '@/features/transactions/components/TransactionsHeader'
import TransactionStatCards from '@/features/transactions/components/TransactionStatCards'
import type { Transaction } from '@/features/transactions/types'
import { useExports } from '@/features/transactions/useExports'
import { useLedger } from '@/features/transactions/useLedger'

export default function TransactionsPage() {
  const ledger = useLedger()
  const exports = useExports(ledger)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [deleting, setDeleting] = useState<Transaction | null>(null)
  const portfolioId = ledger.filters.server.portfolio_id
  const filtered = ledger.filters.active > 0
  const hasRows = ledger.loaded.length > 0

  if (ledger.query.isLoading) {
    return (
      <PageSkeleton
        titre="Transactions"
        description="Chaque mouvement qui a façonné ton patrimoine."
        niveauTitre={2}
        forme="table"
        action
      />
    )
  }

  if (ledger.query.error) {
    return (
      <QueryErrorState error={ledger.query.error} onRetry={ledger.query.refetch} title="Impossible de charger les transactions" />
    )
  }

  return (
    <div className="space-y-6">
      <TransactionsHeader
        portfolioId={portfolioId}
        adding={adding}
        onAddingChange={setAdding}
        exportMenu={
          <ExportMenu
            exports={exports}
            filtered={filtered}
            loadedCount={ledger.loaded.length}
            selectedCount={ledger.selection.ids.size}
          />
        }
      />
      {hasRows && <TransactionStatCards transactions={ledger.loaded} total={ledger.total} filtered={filtered} />}
      <LedgerCard
        ledger={ledger}
        onExportSelected={exports.exportSelected}
        onAdd={() => setAdding(true)}
        onEdit={setEditing}
        onDelete={setDeleting}
      />
      {hasRows && <DangerZone portfolioId={portfolioId} count={ledger.loaded.length} />}
      <EditTransactionForm transaction={editing} open={editing !== null} onOpenChange={(open) => !open && setEditing(null)} />
      <DeleteTransactionDialog transaction={deleting} onClose={() => setDeleting(null)} />
    </div>
  )
}
