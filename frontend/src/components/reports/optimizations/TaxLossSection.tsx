import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { insightsApi, reportsApi, type TaxSummary } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import SharedEmptyState from '@/components/ui/empty-state'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { AlertTriangle, Lightbulb, TrendingUp } from 'lucide-react'
import { Loader } from './shared'

interface TaxLossOpportunity {
  symbol: string
  asset_type: string
  avg_buy_price: number
  current_price: number
  current_value: number
  unrealized_loss: number
  unrealized_loss_pct: number
  potential_tax_saving: number
}

interface HarvestRow extends TaxLossOpportunity {
  /** Économie d'impôt affichée, plafonnée selon le régime fiscal FR (null = plafond non calculable). */
  displayedSaving: number | null
}

function HarvestTable({ rows }: { rows: HarvestRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th scope="col" className="text-left p-2">Actif</th>
            <th scope="col" className="text-right p-2">PRU</th>
            <th scope="col" className="text-right p-2">Prix actuel</th>
            <th scope="col" className="text-right p-2">Valeur</th>
            <th scope="col" className="text-right p-2">Moins-value</th>
            <th scope="col" className="text-right p-2">%</th>
            <th scope="col" className="text-right p-2">Eco. impôt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((op) => (
            <tr key={op.symbol} className="border-b last:border-b-0">
              <td className="p-2">
                <span className="font-medium">{op.symbol}</span>
                <Badge variant="outline" className="ml-1 text-xs">{op.asset_type}</Badge>
              </td>
              <td className="text-right p-2">{formatCurrency(op.avg_buy_price)}</td>
              <td className="text-right p-2">{formatCurrency(op.current_price)}</td>
              <td className="text-right p-2">{formatCurrency(op.current_value)}</td>
              <td className="text-right p-2 text-loss font-medium">{formatCurrency(op.unrealized_loss)}</td>
              <td className="text-right p-2 text-loss">{op.unrealized_loss_pct.toFixed(1)}%</td>
              <td className={`text-right p-2 ${op.displayedSaving && op.displayedSaving > 0 ? 'text-gain' : 'text-muted-foreground'}`}>
                {op.displayedSaving !== null ? formatCurrency(op.displayedSaving) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Tax-Loss Harvesting : opportunités crypto (plafonnées via la synthèse 2086,
 * art. 150 VH bis) et titres (report 10 ans, art. 150-0 D).
 */
export default function TaxLossSection() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.taxLossHarvesting,
    queryFn: insightsApi.getTaxLossHarvesting,
    staleTime: 5 * 60 * 1000,
  })

  // Synthèse fiscale 2086 de l'année en cours : indispensable pour plafonner
  // l'économie crypto (art. 150 VH bis — les MV crypto ne s'imputent que sur
  // les PV crypto de la MÊME année, sans report possible).
  const fiscalYear = new Date().getFullYear()
  const { data: taxSummary } = useQuery<TaxSummary>({
    queryKey: queryKeys.reports.taxSummary(fiscalYear),
    queryFn: () => reportsApi.getTaxSummary(fiscalYear),
    staleTime: 10 * 60_000, // calcul lourd côté back — 10 min de fraîcheur suffisent
    meta: { suppressGlobalError: true }, // best-effort : fallback silencieux
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_candidates === 0) {
    return (
      <SharedEmptyState
        icon={TrendingUp}
        title="Aucune opportunité"
        description="Toutes vos positions sont en plus-value. Pas de tax-loss harvesting possible."
      />
    )
  }

  const opportunities = data.opportunities as TaxLossOpportunity[]
  const cryptoOps = opportunities.filter((op) => op.asset_type === 'crypto')
  const titresOps = opportunities.filter((op) => op.asset_type !== 'crypto')

  // CRYPTO : l'économie n'est réelle que s'il existe des PV crypto imposables
  // la même année. On plafonne cumulativement chaque opportunité à la PV nette
  // YTD restante (min(MV, PV restante) × 30 %). Sans synthèse fiscale → « — ».
  const netPlusValueYtd = taxSummary ? Math.max(0, taxSummary.net_plus_value) : null
  let remainingPv = netPlusValueYtd ?? 0
  const cryptoRows: HarvestRow[] = cryptoOps.map((op) => {
    if (netPlusValueYtd === null) return { ...op, displayedSaving: null }
    const loss = Math.abs(op.unrealized_loss)
    const offsettable = Math.min(loss, remainingPv)
    remainingPv -= offsettable
    return { ...op, displayedSaving: Math.round(offsettable * 0.3 * 100) / 100 }
  })

  // TITRES (actions/ETF…) : MV × 30 %, les moins-values sont reportables 10 ans.
  const titresRows: HarvestRow[] = titresOps.map((op) => ({
    ...op,
    displayedSaving: op.potential_tax_saving,
  }))

  const cryptoSaving = cryptoRows.reduce((sum, r) => sum + (r.displayedSaving ?? 0), 0)
  const titresSaving = titresRows.reduce((sum, r) => sum + (r.displayedSaving ?? 0), 0)
  // Total = somme des économies PLAFONNÉES, jamais la somme brute (MV totale × 30 %).
  const totalSaving = cryptoSaving + titresSaving

  return (
    <div className="space-y-4">
      {/* Fiscal disclaimer */}
      <div className="flex items-start gap-2 rounded-md bg-warning/10 border border-warning/20 px-3 py-2">
        <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
        <p className="text-[11px] text-warning dark:text-warning leading-tight">
          Le Tax-Loss Harvesting est une stratégie fiscale soumise à des règles complexes (wash-sale, règles anti-abus).
          Ces informations sont fournies à titre indicatif uniquement et ne constituent pas un conseil fiscal.
          Consultez un conseiller fiscal agréé avant toute décision.
        </p>
      </div>
      {/* Summary */}
      <SpotlightGroup className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moins-values totales</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">{formatCurrency(data.total_harvestable)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_candidates} positions</p>
          </CardContent>
        </Card>
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Economie d'impôt estimée</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-gain">{formatCurrency(totalSaving)}</div>
            <p className="text-xs text-muted-foreground">
              Flat tax 30 % — plafonnée selon le régime fiscal FR
              {cryptoOps.length > 0 && !taxSummary ? ' (hors crypto : synthèse fiscale indisponible)' : ''}
            </p>
          </CardContent>
        </Card>
        <Card elevation="raised" className="spot-card border-warning/20 bg-warning/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              <Lightbulb className="h-4 w-4 text-warning" />
              Conseil
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">{data.note}</p>
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Crypto opportunities */}
      {cryptoRows.length > 0 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Opportunités crypto</CardTitle>
            <CardDescription>
              Art. 150 VH bis : les moins-values crypto ne s'imputent que sur les plus-values crypto
              de la même année ({fiscalYear}) — aucun report possible. Économie plafonnée à la PV nette
              imposable restante ({netPlusValueYtd !== null ? formatCurrency(netPlusValueYtd) : 'indisponible'} en {fiscalYear}).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {netPlusValueYtd !== null && netPlusValueYtd <= 0 && (
              <div className="flex items-start gap-2 rounded-md bg-muted px-3 py-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground">
                  Aucune PV crypto imposable en {fiscalYear} à compenser — les MV crypto ne se reportent pas.
                  Vendre ces positions maintenant n'apporterait aucune économie d'impôt.
                </p>
              </div>
            )}
            {netPlusValueYtd === null && (
              <div className="flex items-start gap-2 rounded-md bg-muted px-3 py-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground">
                  Synthèse fiscale {fiscalYear} indisponible : le plafond d'imputation crypto ne peut pas
                  être calculé. Aucune économie n'est affichée pour éviter un chiffre surestimé.
                </p>
              </div>
            )}
            <HarvestTable rows={cryptoRows} />
            <p className="text-xs text-muted-foreground">
              Vendre contre un stablecoin ou du fiat uniquement (une cession crypto→crypto n'est pas un
              fait générateur d'imposition et ne cristallise donc pas la moins-value).
              Attention : c'est une cession imposable au sens de l'art. 150 VH bis.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Titres opportunities */}
      {titresRows.length > 0 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Opportunités titres (actions, ETF…)</CardTitle>
            <CardDescription>
              Positions en moins-value pouvant réduire votre impôt (flat tax 30 %)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <HarvestTable rows={titresRows} />
            <p className="text-xs text-muted-foreground">
              Les moins-values sur titres sont imputables sur les plus-values de même nature et
              reportables pendant 10 ans (art. 150-0 D).
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
