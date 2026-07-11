import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import { insightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { ResponsiveBar } from '@nivo/bar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { Loader, SectionEmptyState } from './shared'

/**
 * Revenus passifs (staking, airdrops) : synthèse, projection annuelle et
 * répartitions par mois / type / actif.
 */
export default function PassiveIncomeSection() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.passiveIncome,
    queryFn: () => insightsApi.getPassiveIncome(),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_events === 0) {
    return <SectionEmptyState message="Aucun revenu passif enregistré (staking, airdrops)" />
  }

  const monthlyData = Object.entries((data.by_month ?? {}) as Record<string, number>).map(([month, value]) => ({
    month,
    income: value,
  }))

  const typeLabels: Record<string, string> = {
    staking_reward: 'Reward',
    airdrop: 'Airdrops',
  }

  return (
    <div className="space-y-4">
      <SpotlightGroup className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total revenus passifs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-gain">{formatCurrency(data.total_income)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_events} versements</p>
          </CardContent>
        </Card>
        <StatCard
          className="spot-card"
          label="Moyenne mensuelle"
          value={data.avg_monthly}
          format={formatCurrency}
          hint="par mois"
        />
        <Card elevation="raised" className="spot-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Projection annuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-accent">{formatCurrency(data.projected_annual)}</div>
            <p className="text-xs text-muted-foreground">basé sur les 3 derniers mois</p>
          </CardContent>
        </Card>
      </SpotlightGroup>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Revenus par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveBar
                data={monthlyData}
                keys={['income']}
                indexBy="month"
                theme={theme}
                margin={{ top: 12, right: 16, bottom: 32, left: 56 }}
                padding={0.3}
                colors={() => color('--chart-3')}
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
            <CardTitle>Par type</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries((data.by_type ?? {}) as Record<string, number>).map(([type, value]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{typeLabels[type] || type}</span>
                  <span className="text-sm font-mono text-gain">{formatCurrency(value)}</span>
                </div>
              ))}
              {Object.keys((data.by_asset ?? {}) as Record<string, number>).length > 0 && (
                <>
                  <div className="border-t pt-3 mt-3">
                    <p className="text-xs text-muted-foreground mb-2">Par actif :</p>
                    {Object.entries((data.by_asset ?? {}) as Record<string, number>).map(([sym, val]) => (
                      <div key={sym} className="flex items-center justify-between py-1">
                        <span className="text-sm">{sym}</span>
                        <span className="text-xs font-mono">{formatCurrency(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
