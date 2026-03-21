import { useState } from 'react'
import type { PnLBreakdown } from '@/types'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { Scale, Info, AlertTriangle } from 'lucide-react'

function MetricTooltip({ children, content }: { children: React.ReactNode; content: string }) {
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help inline-flex items-center gap-1">
            {children}
            <Info className="h-3 w-3 text-muted-foreground" />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-sm">{content}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

interface DashboardPnlCardProps {
  pnlBreakdown: PnLBreakdown
  periodLabel?: string
  privacyMode?: boolean
}

export default function DashboardPnlCard({ pnlBreakdown, periodLabel, privacyMode }: DashboardPnlCardProps) {
  const [taxMode, setTaxMode] = useState<'pfu' | 'progressive'>('pfu')
  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)

  // Tax calculation based on selected mode
  const taxRate = taxMode === 'pfu' ? 0.3 : 0  // Progressive = 0% estimate (user must consult advisor)
  const estimatedTax = pnlBreakdown.realized_pnl > 0 ? pnlBreakdown.realized_pnl * taxRate : 0
  const netAfterTax = pnlBreakdown.net_pnl - estimatedTax

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Scale className="h-4 w-4" />Répartition des Plus/Moins-values <span className="text-xs font-normal text-muted-foreground">({periodLabel ?? 'Depuis le début'})</span></CardTitle>
        <CardDescription>Distinction entre gains réalisés et latents (fiscalité)</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <MetricTooltip content="Profits/pertes sur les positions actuellement détenues. Non imposable tant que non vendu."><p className="text-xs text-muted-foreground">P&L Latent</p></MetricTooltip>
            <p className={`text-lg font-bold ${pnlBreakdown.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{pnlBreakdown.unrealized_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.unrealized_pnl)}</p>
          </div>
          <div>
            <MetricTooltip content="Profits/pertes sur les actifs vendus. Soumis à imposition."><p className="text-xs text-muted-foreground">P&L Réalisé</p></MetricTooltip>
            <p className={`text-lg font-bold ${pnlBreakdown.realized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{pnlBreakdown.realized_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.realized_pnl)}</p>
          </div>
          <div>
            <MetricTooltip content="Total des frais de transaction payés."><p className="text-xs text-muted-foreground">Total Frais</p></MetricTooltip>
            <p className="text-lg font-bold text-orange-500">-{pc(pnlBreakdown.total_fees)}</p>
          </div>
          <div>
            <MetricTooltip content="Latent + Réalisé − Frais."><p className="text-xs text-muted-foreground">P&L Net</p></MetricTooltip>
            <p className={`text-lg font-bold ${pnlBreakdown.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{pnlBreakdown.net_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.net_pnl)}</p>
          </div>
        </div>
        {pnlBreakdown.realized_pnl > 0 && (
          <div className="mt-4 pt-3 border-t border-border/50">
            {/* Tax mode toggle */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-muted-foreground">Régime fiscal :</span>
              <div className="inline-flex rounded-md border border-border text-xs">
                <button
                  className={`px-2.5 py-1 rounded-l-md transition-colors ${
                    taxMode === 'pfu'
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted'
                  }`}
                  onClick={() => setTaxMode('pfu')}
                >
                  PFU (30%)
                </button>
                <button
                  className={`px-2.5 py-1 rounded-r-md transition-colors ${
                    taxMode === 'progressive'
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted'
                  }`}
                  onClick={() => setTaxMode('progressive')}
                >
                  Barème progressif
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <MetricTooltip content={
                  taxMode === 'pfu'
                    ? "Prélèvement Forfaitaire Unique (flat tax 30%) : IR 12.8% + Prélèvements Sociaux 17.2%. Appliqué uniquement sur les plus-values réalisées."
                    : "Barème progressif : le taux dépend de votre tranche marginale d'imposition. Consultez votre conseiller fiscal."
                }>
                  <p className="text-xs text-muted-foreground">
                    {taxMode === 'pfu' ? 'PFU estimé (30%)' : 'Impôt estimé (barème)'}
                  </p>
                </MetricTooltip>
                <p className="text-lg font-bold text-orange-500">
                  {estimatedTax > 0 ? `-${pc(estimatedTax)}` : pc(0)}
                </p>
                {taxMode === 'progressive' && (
                  <p className="text-[10px] text-muted-foreground">Dépend de votre TMI</p>
                )}
              </div>
              <div>
                <MetricTooltip content="P&L Net après déduction de l'impôt estimé sur les gains réalisés."><p className="text-xs text-muted-foreground">Net après impôts</p></MetricTooltip>
                <p className={`text-lg font-bold ${netAfterTax >= 0 ? 'text-green-500' : 'text-red-500'}`}>{netAfterTax >= 0 ? '\u25B2' : '\u25BC'} {pc(netAfterTax)}</p>
              </div>
            </div>

            {/* Fiscal disclaimer banner */}
            <div className="mt-3 flex items-start gap-2 rounded-md bg-amber-500/10 border border-amber-500/20 px-3 py-2">
              <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-[11px] text-amber-700 dark:text-amber-400 leading-tight">
                Estimation indicative{taxMode === 'pfu' ? ' basée sur le PFU 30%' : ''}. Ne constitue pas un conseil fiscal.
                Ne prend pas en compte les abattements, le report de moins-values ou votre situation personnelle.
                Consultez votre conseiller fiscal.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
