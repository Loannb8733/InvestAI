import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import type { PnLBreakdown } from '@/types'
import { profileApi, investorProfileQueryKey, reportsApi, type TaxSummary } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
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
  totalDividendIncome?: number
  totalReturn?: number
}

export default function DashboardPnlCard({ pnlBreakdown, periodLabel, privacyMode, totalDividendIncome = 0, totalReturn }: DashboardPnlCardProps) {
  const [taxMode, setTaxMode] = useState<'pfu' | 'progressive'>('pfu')
  const [returnMode, setReturnMode] = useState<'price' | 'total'>('price')
  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)
  const hasDividends = totalDividendIncome > 0

  // Vraie base imposable : synthèse 2086 de l'année fiscale EN COURS
  // (cessions crypto→fiat uniquement, méthode d'acquisition globale) — pas
  // le « réalisé all-time × 30 % » qui cumulait toutes les années et incluait
  // les conversions crypto↔crypto.
  const fiscalYear = new Date().getFullYear()
  const { data: taxSummary } = useQuery<TaxSummary>({
    queryKey: queryKeys.reports.taxSummary(fiscalYear),
    queryFn: () => reportsApi.getTaxSummary(fiscalYear),
    staleTime: 10 * 60_000, // calcul lourd côté back — 10 min de fraîcheur suffisent
    meta: { suppressGlobalError: true }, // best-effort : fallback silencieux
  })

  // TMI du profil investisseur (Réglages) : si renseignée, le mode barème
  // affiche PS 17,2 % + IR à la TMI au lieu du seul plancher PS.
  const { data: investorProfile } = useQuery({
    queryKey: investorProfileQueryKey,
    queryFn: profileApi.getInvestorProfile,
    staleTime: 10 * 60_000, // le profil change rarement
    meta: { suppressGlobalError: true }, // best-effort : fallback silencieux
  })
  const tmiRate = investorProfile?.tmi_rate ?? null
  const tmiPct = tmiRate != null ? Math.round(tmiRate * 100) : null

  // PFU = flat tax 30 % sur la PV nette 2086 ; barème = PS 17,2 % toujours
  // dus + IR à la TMI si connue (sinon plancher PS seul, jamais 0 fictif).
  const taxableBase = taxSummary ? Math.max(0, taxSummary.net_plus_value) : null
  const progressiveBase = taxableBase ?? Math.max(0, pnlBreakdown.realized_pnl)
  const progressiveRate = 0.172 + (tmiRate ?? 0)
  const estimatedTax =
    taxSummary != null
      ? taxMode === 'pfu'
        ? Math.max(0, taxSummary.flat_tax_30)
        : tmiRate != null
          ? progressiveBase * progressiveRate
          : Math.max(0, taxSummary.ps_17_2)
      : // Fallback (synthèse indisponible) : ancien calcul conservateur all-time
        pnlBreakdown.realized_pnl > 0
        ? pnlBreakdown.realized_pnl * (taxMode === 'pfu' ? 0.3 : progressiveRate)
        : 0
  const netAfterTax = pnlBreakdown.net_pnl - estimatedTax
  const hasTaxSection = pnlBreakdown.realized_pnl > 0 || (taxSummary?.nb_cessions ?? 0) > 0

  return (
    <Card elevation="raised">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Scale className="h-4 w-4" />Répartition des Plus/Moins-values <span className="text-xs font-normal text-muted-foreground">({periodLabel ?? 'Depuis le début'})</span></CardTitle>
        <CardDescription>Distinction entre gains réalisés et latents (fiscalité)</CardDescription>
      </CardHeader>
      <CardContent>
        {hasDividends && (
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-muted-foreground">Rendement :</span>
            <div className="inline-flex rounded-md border border-border text-xs">
              <button
                type="button"
                aria-pressed={returnMode === 'price'}
                className={`px-2.5 py-1 rounded-l-md transition-colors ${
                  returnMode === 'price'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                }`}
                onClick={() => setReturnMode('price')}
              >
                Price Return
              </button>
              <button
                type="button"
                aria-pressed={returnMode === 'total'}
                className={`px-2.5 py-1 rounded-r-md transition-colors ${
                  returnMode === 'total'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                }`}
                onClick={() => setReturnMode('total')}
              >
                Total Return
              </button>
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <MetricTooltip content="Profits/pertes sur les positions actuellement détenues. Non imposable tant que non vendu."><p className="text-xs text-muted-foreground">P&L Latent</p></MetricTooltip>
            <p className={`text-lg font-bold ${pnlBreakdown.unrealized_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>{pnlBreakdown.unrealized_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.unrealized_pnl)}</p>
          </div>
          <div>
            <MetricTooltip content="Profits/pertes sur les actifs vendus. Soumis à imposition."><p className="text-xs text-muted-foreground">P&L Réalisé</p></MetricTooltip>
            <p className={`text-lg font-bold ${pnlBreakdown.realized_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>{pnlBreakdown.realized_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.realized_pnl)}</p>
          </div>
          <div>
            <MetricTooltip content="Total des frais de transaction payés."><p className="text-xs text-muted-foreground">Total Frais</p></MetricTooltip>
            <p className="text-lg font-bold text-warning">-{pc(pnlBreakdown.total_fees)}</p>
          </div>
          <div>
            <MetricTooltip content={returnMode === 'total' ? "P&L Net + Dividendes & Rewards (Total Return)." : "Latent + Réalisé − Frais."}>
              <p className="text-xs text-muted-foreground">{returnMode === 'total' ? 'Total Return' : 'P&L Net'}</p>
            </MetricTooltip>
            {returnMode === 'total' && totalReturn != null ? (
              <p className={`text-lg font-bold ${totalReturn >= 0 ? 'text-gain' : 'text-loss'}`}>{totalReturn >= 0 ? '\u25B2' : '\u25BC'} {pc(totalReturn)}</p>
            ) : (
              <p className={`text-lg font-bold ${pnlBreakdown.net_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>{pnlBreakdown.net_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.net_pnl)}</p>
            )}
          </div>
        </div>
        {returnMode === 'total' && hasDividends && (
          <div className="mt-3 pt-3 border-t border-border/50 grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <MetricTooltip content="Revenus de dividendes et staking rewards cumulés."><p className="text-xs text-muted-foreground">Dividendes & Rewards</p></MetricTooltip>
              <p className="text-lg font-bold text-gain">+{pc(totalDividendIncome)}</p>
            </div>
            <div>
              <MetricTooltip content="Plus-value hors dividendes (variation du prix des actifs)."><p className="text-xs text-muted-foreground">Price Return</p></MetricTooltip>
              <p className={`text-lg font-bold ${pnlBreakdown.net_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>{pnlBreakdown.net_pnl >= 0 ? '\u25B2' : '\u25BC'} {pc(pnlBreakdown.net_pnl)}</p>
            </div>
          </div>
        )}
        {hasTaxSection && (
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
                    ? `Prélèvement Forfaitaire Unique (flat tax 30 %) : IR 12,8 % + PS 17,2 %. ${taxSummary ? `Base 2086 ${fiscalYear} : PV nette de ${formatCurrency(taxSummary.net_plus_value)} sur ${taxSummary.nb_cessions} cession(s) crypto→fiat.` : 'Base : réalisé cumulé (synthèse annuelle indisponible).'}`
                    : tmiRate != null
                      ? `Barème progressif avec votre TMI : PS 17,2 % (${formatCurrency(progressiveBase * 0.172)}) + IR ${tmiPct} % (${formatCurrency(progressiveBase * tmiRate)}) sur une base imposable de ${formatCurrency(progressiveBase)}. TMI configurable dans les Réglages.`
                      : "Barème progressif : les prélèvements sociaux (17,2 %) restent dus dans tous les cas ; l'impôt sur le revenu s'ajoute selon votre tranche marginale d'imposition."
                }>
                  <p className="text-xs text-muted-foreground">
                    {taxMode === 'pfu'
                      ? taxSummary ? `PFU ${fiscalYear} (base 2086)` : 'PFU estimé (30 %)'
                      : tmiRate != null
                        ? `Barème : PS 17,2 % + IR ${tmiPct} %${taxSummary ? ` (${fiscalYear})` : ''}`
                        : `PS 17,2 %${taxSummary ? ` ${fiscalYear}` : ''} (plancher barème)`}
                  </p>
                </MetricTooltip>
                <p className="text-lg font-bold text-warning">
                  {estimatedTax > 0 ? `-${pc(estimatedTax)}` : pc(0)}
                </p>
                {taxMode === 'progressive' && tmiRate == null && (
                  <p className="text-[10px] text-muted-foreground">
                    + IR selon votre TMI —{' '}
                    <Link to="/settings" className="underline hover:text-foreground">
                      Configurer votre TMI dans les Réglages
                    </Link>
                  </p>
                )}
                {taxSummary && taxableBase === 0 && (
                  <p className="text-[10px] text-muted-foreground">Aucune PV nette imposable en {fiscalYear}</p>
                )}
              </div>
              <div>
                <MetricTooltip content="P&L Net après déduction de l'impôt estimé sur les gains réalisés."><p className="text-xs text-muted-foreground">Net après impôts</p></MetricTooltip>
                <p className={`text-lg font-bold ${netAfterTax >= 0 ? 'text-gain' : 'text-loss'}`}>{netAfterTax >= 0 ? '\u25B2' : '\u25BC'} {pc(netAfterTax)}</p>
              </div>
            </div>

            {/* Fiscal disclaimer banner */}
            <div className="mt-3 flex items-start gap-2 rounded-md bg-warning/10 border border-warning/20 px-3 py-2">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <p className="text-[11px] text-warning dark:text-warning leading-tight">
                {taxSummary
                  ? `Base : formulaire 2086 ${fiscalYear} (cessions crypto→fiat, méthode d'acquisition globale, moins-values de l'année déduites). Hors report des moins-values antérieures et cas particuliers.`
                  : "Estimation conservative sur le P&L réalisé cumulé (toutes années) — le montant réel sera inférieur."}{' '}
                Ne constitue pas un conseil fiscal.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
