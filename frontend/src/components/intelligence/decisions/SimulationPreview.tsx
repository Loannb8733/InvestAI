import { formatCurrency, formatDate } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { History, Info } from 'lucide-react'
import { ACTION_LABELS, type Backtest, type Simulation } from './simulatorModel'

const eur = (value: number | null | undefined) => (value == null ? '—' : formatCurrency(value, 'EUR'))

function BacktestSummary({ backtest, template }: { backtest: Backtest; template: Simulation['template'] }) {
  if (!backtest.available) {
    return <p className="text-sm text-muted-foreground">Simulation passée indisponible : {backtest.reason}</p>
  }
  const investedLabel = template === 'profit_taking' ? 'Valeur de départ' : 'Montant investi'
  const pnlClass = (backtest.pnl_eur ?? 0) >= 0 ? 'text-gain' : 'text-loss'
  return (
    <div className="space-y-2">
      <p className="text-sm">
        Si cette règle avait été appliquée du {formatDate(backtest.start_date)} au {formatDate(backtest.end_date)} (
        {backtest.events_simulated} sur {backtest.events_planned} échéances) :
      </p>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">{investedLabel}</dt>
          <dd className="font-medium">{eur(backtest.invested_eur)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Ventes</dt>
          <dd className="font-medium">{eur(backtest.withdrawn_eur)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Valeur finale</dt>
          <dd className="font-medium">{eur(backtest.final_value_eur)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Résultat</dt>
          <dd className={`font-medium ${pnlClass}`}>
            {eur(backtest.pnl_eur)}
            {backtest.pnl_pct != null && ` (${backtest.pnl_pct.toFixed(2)} %)`}
          </dd>
        </div>
      </dl>
      {backtest.benchmark_label && (
        <p className="text-sm text-muted-foreground">
          Référence « {backtest.benchmark_label} » : {eur(backtest.benchmark_value_eur)}
        </p>
      )}
      {backtest.missing_prices > 0 && (
        <p className="text-xs text-muted-foreground">{backtest.missing_prices} prix manquant(s) : achats non simulés.</p>
      )}
      <p className="text-xs text-muted-foreground italic">{backtest.note}</p>
    </div>
  )
}

export default function SimulationPreview({ simulation }: { simulation: Simulation }) {
  return (
    <section aria-label="Aperçu de l'échéancier" className="space-y-4 rounded-lg border border-border p-4">
      <p className="text-sm font-medium">{simulation.rule_summary}</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Échéance</TableHead>
            <TableHead>Opération</TableHead>
            <TableHead>Actif</TableHead>
            <TableHead className="text-right">Montant</TableHead>
            <TableHead>Détail</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {simulation.schedule.map((line, idx) => (
            <TableRow key={idx}>
              <TableCell className="whitespace-nowrap">
                {line.date ? formatDate(line.date) : `Cours ≥ ${eur(line.trigger_price)}`}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{ACTION_LABELS[line.action] ?? line.action}</Badge>
              </TableCell>
              <TableCell>{line.symbol ?? '—'}</TableCell>
              <TableCell className="text-right whitespace-nowrap">
                {line.amount != null ? eur(line.amount) : line.action === 'REVIEW' ? '—' : 'À l’échéance'}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">{line.note}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="text-sm">
        Total des achats prévus : <span className="font-medium">{eur(simulation.total_buy_eur)}</span>
        {simulation.total_sell_eur > 0 && (
          <>
            {' '}· ventes : <span className="font-medium">{eur(simulation.total_sell_eur)}</span>
          </>
        )}
        {simulation.has_amounts_at_execution && ' · certains montants se calculent à l’échéance'}
      </p>
      {simulation.backtest && (
        <div className="rounded-md bg-muted/30 p-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <History className="h-3.5 w-3.5" />
            Simulation sur l’historique
          </p>
          <BacktestSummary backtest={simulation.backtest} template={simulation.template} />
        </div>
      )}
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
        {simulation.disclaimer}
      </p>
    </section>
  )
}
