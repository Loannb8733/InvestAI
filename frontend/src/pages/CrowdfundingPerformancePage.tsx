import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { TrendingUp, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { ResponsiveBar } from '@nivo/bar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { CrowdfundingPerformanceItem } from '@/types/crowdfunding'

export default function CrowdfundingPerformancePage() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery<{ projects: CrowdfundingPerformanceItem[] }>({
    queryKey: queryKeys.crowdfunding.performance,
    queryFn: crowdfundingApi.getPerformance,
  })

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SkeletonStatCard />
        <SkeletonStatCard />
        <SkeletonStatCard />
      </div>
    )
  }

  const projects = data?.projects || []

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-serif font-medium">Performance Crowdfunding</h1>
          <p className="text-muted-foreground">Aucun projet à analyser</p>
        </div>
      </div>
    )
  }

  // Aggregated metrics
  const totalInvested = projects.reduce((s, p) => s + p.invested_amount, 0)
  const totalProjectedInterest = projects.reduce((s, p) => s + p.projected_total_interest, 0)
  const totalReceived = projects.reduce((s, p) => s + p.total_received, 0)
  const onTrackCount = projects.filter((p) => p.on_track && p.status === 'active').length
  const activeCount = projects.filter((p) => p.status === 'active').length

  // Chart data
  const chartData = projects
    .filter((p) => p.status !== 'completed')
    .map((p) => ({
      name: (p.project_name || p.platform).substring(0, 20),
      'Intérêts projetés': p.projected_total_interest,
      'Reçu': p.total_received,
    }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-medium">Performance Crowdfunding</h1>
        <p className="text-muted-foreground">
          Suivi des rendements projetés vs réalisés
        </p>
      </div>

      {/* Summary cards */}
      <SpotlightGroup className="grid gap-4 md:grid-cols-3">
        <StatCard
          className="spot-card"
          label="Intérêts Projetés (Total)"
          icon={TrendingUp}
          value={totalProjectedInterest}
          format={formatCurrency}
          hint={<>sur {formatCurrency(totalInvested)} investis</>}
        />
        <StatCard
          className="spot-card"
          label="Total Reçu"
          icon={CheckCircle2}
          value={totalReceived}
          format={formatCurrency}
          hint={
            totalProjectedInterest > 0
              ? `${((totalReceived / totalProjectedInterest) * 100).toFixed(0)}% des intérêts projetés`
              : '—'
          }
        />
        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Projets On Track</CardTitle>
            {onTrackCount === activeCount ? (
              <CheckCircle2 className="h-4 w-4 text-gain" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-warning" />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium">
              {onTrackCount}/{activeCount}
            </div>
            <p className="text-xs text-muted-foreground">
              {onTrackCount === activeCount
                ? 'Tous les projets actifs sont à jour'
                : `${activeCount - onTrackCount} projet(s) en retard`}
            </p>
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Chart: Projected vs Received */}
      {chartData.length > 0 && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Projeté vs Reçu par Projet</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveBar
                data={chartData}
                keys={['Intérêts projetés', 'Reçu']}
                indexBy="name"
                groupMode="grouped"
                theme={theme}
                margin={{ top: 28, right: 16, bottom: 40, left: 56 }}
                padding={0.25}
                innerPadding={4}
                colors={({ id }) =>
                  id === 'Intérêts projetés' ? color('--primary', 0.3) : color('--chart-3')
                }
                borderRadius={4}
                enableLabel={false}
                enableGridY
                axisBottom={{ tickSize: 0, tickPadding: 8 }}
                axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}€` }}
                valueScale={{ type: 'linear' }}
                tooltip={({ id, value, indexValue, color: barColor }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="text-xs font-medium">{indexValue}</p>
                    <span className="mt-0.5 flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-[2px]"
                        style={{ backgroundColor: barColor }}
                      />
                      <span className="text-xs text-muted-foreground">{id}</span>
                    </span>
                    <p className="mt-0.5 font-mono text-sm tabular-nums">
                      {formatCurrency(value)}
                    </p>
                  </div>
                )}
                legends={[
                  {
                    anchor: 'top-right',
                    direction: 'row',
                    translateY: -22,
                    itemWidth: 70,
                    itemHeight: 18,
                    symbolSize: 10,
                    symbolShape: 'circle',
                    itemTextColor: color('--muted-foreground'),
                    dataFrom: 'keys',
                  },
                ]}
                animate
                motionConfig="gentle"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Detail table */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Détail par Projet</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th scope="col" className="pb-2 font-medium">Projet</th>
                  <th scope="col" className="pb-2 font-medium">Plateforme</th>
                  <th scope="col" className="pb-2 font-medium text-right">Investi</th>
                  <th scope="col" className="pb-2 font-medium text-right">Taux</th>
                  <th scope="col" className="pb-2 font-medium text-right">Projeté</th>
                  <th scope="col" className="pb-2 font-medium text-right">Reçu</th>
                  <th scope="col" className="pb-2 font-medium text-center">Progression</th>
                  <th scope="col" className="pb-2 font-medium text-center">Statut</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id} className="border-b border-border/50 last:border-0">
                    <td className="py-3 max-w-[200px] truncate">
                      {p.project_name || '—'}
                    </td>
                    <td className="py-3 text-muted-foreground">{p.platform}</td>
                    <td className="py-3 text-right">{formatCurrency(p.invested_amount)}</td>
                    <td className="py-3 text-right">{p.annual_rate}%</td>
                    <td className="py-3 text-right text-gain">
                      {formatCurrency(p.projected_total_interest)}
                    </td>
                    <td className="py-3 text-right">{formatCurrency(p.total_received)}</td>
                    <td className="py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full"
                            style={{ width: `${Math.min(100, p.progress_percent)}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground w-10">
                          {p.progress_percent}%
                        </span>
                      </div>
                    </td>
                    <td className="py-3 text-center">
                      {p.on_track ? (
                        <Badge variant="secondary" className="bg-gain/10 text-gain">
                          OK
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-warning/10 text-warning">
                          Retard
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
