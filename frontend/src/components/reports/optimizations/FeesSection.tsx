import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { dashboardApi, insightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { ResponsiveBar } from '@nivo/bar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { Info } from 'lucide-react'
import { Loader, SectionEmptyState } from './shared'

/**
 * Analyse des frais : cartes de synthèse, fee drag (coût composé) et
 * répartition par mois / par exchange.
 */
export default function FeesSection() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.fees,
    queryFn: insightsApi.getFees,
    staleTime: 5 * 60 * 1000,
  })
  // Valeur du portefeuille pour mettre les frais en perspective (fee drag).
  const { data: metrics } = useQuery<{ total_value: number }>({
    queryKey: queryKeys.dashboard.metrics(30),
    queryFn: () => dashboardApi.getMetrics(30),
    staleTime: 5 * 60 * 1000,
    meta: { suppressGlobalError: true },
  })

  if (isLoading) return <Loader />

  if (!data || data.total_fees === 0) {
    return <SectionEmptyState message="Aucun frais enregistré" />
  }

  // Fee drag : les frais en % du portefeuille + leur coût composé.
  // Hypothèse de rendement r = 5 %/an (affichée) ; coût 10 ans =
  // V × ((1+r)^10 − (1+r−f)^10) — l'écart de capitalisation dû aux frais.
  const portfolioValue = metrics?.total_value ?? 0
  const annualFees = (data.avg_monthly_fee ?? 0) * 12
  const feeRate = portfolioValue > 0 ? annualFees / portfolioValue : null
  const GROWTH = 0.05
  const compounded10y =
    feeRate !== null && feeRate < GROWTH
      ? portfolioValue * (Math.pow(1 + GROWTH, 10) - Math.pow(1 + GROWTH - feeRate, 10))
      : null
  const costPerTenthPercent = portfolioValue * (Math.pow(1.05, 10) - Math.pow(1.049, 10))

  const monthlyData = Object.entries((data.by_month ?? {}) as Record<string, number>).map(([month, value]) => ({
    month,
    fees: value,
  }))

  const exchangeData = Object.entries((data.by_exchange ?? {}) as Record<string, number>).map(([name, value]) => ({
    name,
    fees: value,
  }))

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <SpotlightGroup className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total des frais</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">{formatCurrency(data.total_fees)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_transactions_with_fees} transactions</p>
          </CardContent>
        </Card>
        <StatCard
          className="spot-card"
          label="Moyenne mensuelle"
          value={data.avg_monthly_fee}
          format={formatCurrency}
          hint="par mois"
        />
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top exchange</CardTitle>
          </CardHeader>
          <CardContent>
            {exchangeData.length > 0 ? (
              <>
                <div className="text-2xl font-serif font-medium">{exchangeData[0].name}</div>
                <p className="text-xs text-muted-foreground">{formatCurrency(exchangeData[0].fees)}</p>
              </>
            ) : (
              <div className="text-muted-foreground">—</div>
            )}
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Fee drag : mise en perspective — c'est le coût composé qui parle,
          pas le montant mensuel. */}
      {feeRate !== null && (
        <Card elevation="raised">
          <CardContent className="pt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
            <div>
              <span className="text-xs text-muted-foreground">Frais annualisés</span>
              <p className={`text-lg font-semibold tabular ${feeRate > 0.005 ? 'text-warning' : 'text-foreground'}`}>
                {(feeRate * 100).toFixed(2)} % <span className="text-xs font-normal text-muted-foreground">du portefeuille</span>
              </p>
            </div>
            {compounded10y !== null && (
              <div>
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-xs text-muted-foreground cursor-help inline-flex items-center gap-1">
                        Coût composé sur 10 ans
                        <Info className="h-3 w-3" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      <p className="text-sm">
                        Écart de capitalisation dû aux frais, à taille de portefeuille constante et
                        hypothèse de rendement 5 %/an : V × ((1+5 %)¹⁰ − (1+5 %−frais)¹⁰).
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <p className="text-lg font-semibold tabular text-loss">≈ {formatCurrency(compounded10y)}</p>
              </div>
            )}
            {portfolioValue > 0 && (
              <p className="text-xs text-muted-foreground basis-full">
                Chaque 0,1 % de frais annuels coûte ≈ {formatCurrency(costPerTenthPercent)} sur 10 ans à
                taille de portefeuille constante.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Frais par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveBar
                data={monthlyData}
                keys={['fees']}
                indexBy="month"
                theme={theme}
                margin={{ top: 12, right: 16, bottom: 32, left: 56 }}
                padding={0.3}
                colors={() => color('--chart-4')}
                borderRadius={4}
                enableLabel={false}
                enableGridY
                axisBottom={{ tickSize: 0, tickPadding: 8 }}
                axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}€` }}
                valueScale={{ type: 'linear' }}
                tooltip={({ indexValue, value }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="mb-0.5 text-xs text-muted-foreground">{indexValue}</p>
                    <p className="font-mono text-sm tabular-nums">{formatCurrency(value)}</p>
                  </div>
                )}
                animate
                motionConfig="gentle"
              />
            </div>
          </CardContent>
        </Card>

        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Frais par exchange</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {exchangeData.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{item.name}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-loss rounded-full"
                        style={{ width: `${data.total_fees > 0 ? Math.min(100, (item.fees / data.total_fees) * 100) : 0}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono w-20 text-right">{formatCurrency(item.fees)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
