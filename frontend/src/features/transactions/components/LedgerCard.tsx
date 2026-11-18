import { AlertTriangle, FileText, Plus, Search, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import type { Transaction } from '../types'
import type { Ledger } from '../useLedger'
import FilterBadges from './FilterBadges'
import FilterBar from './FilterBar'
import LedgerPagination from './LedgerPagination'
import SelectionBar from './SelectionBar'
import TransactionTable from './TransactionTable'

interface LedgerCardProps {
  ledger: Ledger
  onExportSelected: () => void
  onAdd: () => void
  onEdit: (tx: Transaction) => void
  onDelete: (tx: Transaction) => void
}

function NoRows({ filtered, onClear, onAdd }: { filtered: boolean; onClear: () => void; onAdd: () => void }) {
  return (
    <EmptyState
      variant={filtered ? 'search' : 'empty'}
      icon={FileText}
      title={filtered ? 'Aucun résultat' : 'Aucune transaction'}
      description={
        filtered
          ? 'Essayez de modifier vos filtres pour trouver des transactions.'
          : 'Ajoutez votre première transaction ou importez un fichier CSV.'
      }
      action={
        filtered ? (
          <Button variant="outline" onClick={onClear}>
            <X className="h-4 w-4 mr-2" />
            Effacer les filtres
          </Button>
        ) : (
          <Button onClick={onAdd}>
            <Plus className="h-4 w-4 mr-2" />
            Ajouter une transaction
          </Button>
        )
      }
    />
  )
}

export default function LedgerCard({ ledger, onExportSelected, onAdd, onEdit, onDelete }: LedgerCardProps) {
  const { filters, selection } = ledger
  const filtered = filters.active > 0
  return (
    <Card elevation="raised">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle className="flex items-center gap-2">
              Historique
              <Badge variant="secondary">{ledger.loaded.length}</Badge>
            </CardTitle>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Rechercher..."
                value={filters.values.search}
                onChange={(e) => filters.set.search(e.target.value)}
                className="pl-9 pr-9"
              />
              {filters.values.search && (
                <button
                  onClick={() => filters.set.search('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
          <FilterBar portfolios={ledger.portfolios} filters={filters} transactions={ledger.loaded} />
          {filtered && <FilterBadges filters={filters} />}
          {selection.ids.size > 0 && <SelectionBar ids={selection.ids} onExport={onExportSelected} onClear={selection.clear} />}
        </div>
      </CardHeader>
      <CardContent>
        {filtered && ledger.hasMore && (
          <div className="flex items-start gap-2 mb-4 px-3 py-2 rounded-md border border-warning/30 bg-warning/10 text-sm text-warning">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>
              Filtres appliqués sur les {ledger.loaded.length} transactions chargées — les suivantes n'ont pas été parcourues.{' '}
              <button type="button" className="underline underline-offset-2 hover:opacity-80 font-medium" onClick={ledger.loadMore}>
                Charger plus
              </button>{' '}
              pour une vue exhaustive.
            </span>
          </div>
        )}
        {ledger.visible.length > 0 ? (
          <>
            <TransactionTable ledger={ledger} onEdit={onEdit} onDelete={onDelete} />
            {ledger.pageCount > 1 && <LedgerPagination ledger={ledger} />}
            {ledger.hasMore && (
              <div className="flex justify-center mt-4">
                <Button variant="outline" onClick={ledger.loadMore}>
                  Charger plus de transactions
                </Button>
              </div>
            )}
          </>
        ) : (
          <NoRows filtered={filtered} onClear={filters.clear} onAdd={onAdd} />
        )}
      </CardContent>
    </Card>
  )
}
