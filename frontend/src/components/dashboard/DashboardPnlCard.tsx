import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { Scale, Info } from 'lucide-react'

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

interface PnLBreakdown {
  realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
  total_fees: number
  net_pnl: number
}

interface DashboardPnlCardProps {
  pnlBreakdown: PnLBreakdown
  periodLabel?: string
  privacyMode?: boolean
}

export default function DashboardPnlCard({ pnlBreakdown, periodLabel, privacyMode }: DashboardPnlCardProps) {
  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)
  // PFU 30% = IR 12.8% + PS 17.2% — only on realized gains (if positive)
  const estimatedPfu = pnlBreakdown.realized_pnl > 0 ? pnlBreakdown.realized_pnl * 0.3 : 0
  const netAfterTax = pnlBreakdown.net_pnl - estimatedPfu
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
        {estimatedPfu > 0 && (
          <div className="mt-4 pt-3 border-t border-border/50">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <MetricTooltip content="Prélèvement Forfaitaire Unique (flat tax 30%) : IR 12.8% + Prélèvements Sociaux 17.2%. Appliqué uniquement sur les plus-values réalisées."><p className="text-xs text-muted-foreground">PFU estimé (30%)</p></MetricTooltip>
                <p className="text-lg font-bold text-orange-500">-{pc(estimatedPfu)}</p>
              </div>
              <div>
                <MetricTooltip content="P&L Net après déduction du PFU 30% sur les gains réalisés. Valeur réelle de votre patrimoine après impôts."><p className="text-xs text-muted-foreground">Net après impôts</p></MetricTooltip>
                <p className={`text-lg font-bold ${netAfterTax >= 0 ? 'text-green-500' : 'text-red-500'}`}>{netAfterTax >= 0 ? '\u25B2' : '\u25BC'} {pc(netAfterTax)}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
