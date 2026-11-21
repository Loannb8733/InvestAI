import { FileSpreadsheet, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PERIOD_OPTIONS, type RiskPillar } from '../useRiskPillar'

interface ScopeToolbarProps {
  scope: RiskPillar['scope']
  onExport: () => void
  onRefresh: () => void
  refreshing: boolean
}

export default function ScopeToolbar({ scope, onExport, onRefresh, refreshing }: ScopeToolbarProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-muted-foreground">
        Période et portefeuille communs à tout le pilier — score, métriques et
        optimisations parlent de la même fenêtre.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={scope.portfolio} onValueChange={scope.setPortfolio}>
          <SelectTrigger className="w-40" aria-label="Portefeuille analysé">
            <SelectValue placeholder="Portefeuille" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous les portefeuilles</SelectItem>
            {scope.portfolios?.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={scope.period} onValueChange={scope.setPeriod}>
          <SelectTrigger className="w-28" aria-label="Période d'analyse">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIOD_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={onExport}>
          <FileSpreadsheet className="h-4 w-4 mr-1" />
          CSV
        </Button>
        <Button variant="outline" size="icon" onClick={onRefresh} disabled={refreshing} aria-label="Actualiser le score de santé">
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
      </div>
    </div>
  )
}
