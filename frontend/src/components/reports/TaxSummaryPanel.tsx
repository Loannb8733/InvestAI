import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Receipt, TrendingDown, TrendingUp, Scale } from 'lucide-react'
import { reportsApi, type TaxSummary } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import SpotlightGroup from '@/components/ui/spotlight-group'
import StatCard from '@/components/ui/stat-card'
import { Skeleton } from '@/components/ui/skeleton'
import { formatCurrency } from '@/lib/utils'

/**
 * Synthèse fiscale 2086 à l'écran — la fiscalité en continu, pas une fois
 * par an au moment du PDF.
 *
 * Affiche pour l'année choisie : cessions imposables, PV/MV, PV nette et la
 * décomposition du PFU au taux de l'année renvoyé par l'API (31,4 % = IR
 * 12,8 % + PS 18,6 % dès les revenus 2025, 30 % avant) — la vraie base (méthode
 * du portefeuille, cessions crypto→fiat uniquement, échanges crypto→crypto en
 * sursis, exonération si les cessions de l'année n'excèdent pas 305 €).
 * Rappelle la règle française : les moins-values crypto ne se reportent PAS
 * d'une année sur l'autre (art. 150 VH bis).
 */

const CURRENT_YEAR = new Date().getFullYear()

type TaxSummaryWithRates = TaxSummary & {
  pfu_rate?: number
  pfu_total?: number
  pfu_ir?: number
  pfu_ps?: number
  exempt?: boolean
  exemption_threshold?: number
}

const formatRate = (rate: number) =>
  `${(rate * 100).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`

export default function TaxSummaryPanel() {
  const [year, setYear] = useState(CURRENT_YEAR)

  const { data, isLoading } = useQuery<TaxSummaryWithRates>({
    queryKey: queryKeys.reports.taxSummary(year),
    queryFn: () => reportsApi.getTaxSummary(year),
    staleTime: 10 * 60_000,
    meta: { suppressGlobalError: true },
  })

  const years = Array.from({ length: 6 }, (_, i) => CURRENT_YEAR - i)

  return (
    <Card elevation="raised">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base font-medium flex items-center gap-2">
              <Receipt className="h-4 w-4" aria-hidden />
              Synthèse fiscale {year}
            </CardTitle>
            <CardDescription>
              Base 2086 : cessions crypto→fiat, méthode d'acquisition globale
            </CardDescription>
          </div>
          <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
            <SelectTrigger className="w-28" aria-label="Année fiscale">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {years.map((y) => (
                <SelectItem key={y} value={String(y)}>
                  {y}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : (
          <>
            <SpotlightGroup className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <StatCard
                className="spot-card"
                label="Cessions imposables"
                icon={Scale}
                value={data.total_cessions}
                format={formatCurrency}
                hint={<>{data.nb_cessions} cession{data.nb_cessions > 1 ? 's' : ''} crypto→fiat</>}
                static
              />
              <StatCard
                className="spot-card"
                label="Plus-values"
                icon={TrendingUp}
                value={data.total_plus_values}
                format={formatCurrency}
                static
              />
              <StatCard
                className="spot-card"
                label="Moins-values"
                icon={TrendingDown}
                value={data.total_moins_values}
                format={formatCurrency}
                static
              />
              <StatCard
                className="spot-card"
                label="PV nette imposable"
                icon={Receipt}
                value={data.net_plus_value}
                format={formatCurrency}
                delta={data.net_plus_value > 0 ? undefined : undefined}
                hint={
                  data.exempt ? (
                    <>Exonéré : cessions de l'année ≤ {formatCurrency(data.exemption_threshold ?? 305)}</>
                  ) : data.net_plus_value > 0 ? (
                    <>
                      PFU {formatRate(data.pfu_rate ?? 0.3)} :{' '}
                      <strong>{formatCurrency(data.pfu_total ?? data.flat_tax_30)}</strong> (IR{' '}
                      {formatCurrency(data.pfu_ir ?? data.ir_12_8)} + PS{' '}
                      {formatCurrency(data.pfu_ps ?? data.ps_17_2)})
                    </>
                  ) : (
                    <>Aucun impôt dû sur {year}</>
                  )
                }
                static
              />
            </SpotlightGroup>
            {data.net_plus_value < 0 && (
              <p className="text-xs text-muted-foreground">
                ⚠ Les moins-values crypto ne sont <strong>pas reportables</strong> d'une année sur
                l'autre (art. 150 VH bis) : elles ne s'imputent que sur les plus-values de la même
                année. Une MV nette {year} est fiscalement perdue.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
