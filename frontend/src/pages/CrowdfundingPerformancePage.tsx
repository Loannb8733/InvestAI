import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { TrendingUp, AlertTriangle, CheckCircle2, Percent } from 'lucide-react'
import { ResponsiveBar } from '@nivo/bar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { CrowdfundingPerformanceItem } from '@/types/crowdfunding'

/** Format FR d'un pourcentage : « 8,42 % ». */
const formatPercent = (n: number) => `${n.toFixed(2).replace('.', ',')} %`

/** Format FR d'un écart en points de % : « +1,3 pt » / « −2,8 pts ». */
const formatGapPts = (gap: number) => {
  const abs = Math.abs(gap)
  const sign = gap >= 0 ? '+' : '−'
  const unit = abs >= 2 ? 'pts' : 'pt'
  return `${sign}${abs.toFixed(1).replace('.', ',')} ${unit}`
}

/** Couleur de l'écart XIRR vs contractuel : gain ≥ 0, warning [−2 ; 0[, loss < −2 pts. */
const gapColorClass = (gap: number) =>
  gap >= 0 ? 'text-gain' : gap >= -2 ? 'text-warning' : 'text-loss'

/** Tiret « — » avec info-bulle pour un XIRR non calculable. */
function XirrUnavailable() {
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help text-muted-foreground">—</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs text-xs">
          Calculable après 30 jours et premiers flux
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export default function CrowdfundingPerformancePage() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery<{ projects: CrowdfundingPerformanceItem[] }>({
    queryKey: queryKeys.crowdfunding.performance,
    queryFn: crowdfundingApi.getPerformance,
  })

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SkeletonStatCard />
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

  // Aggregated metrics — brut/brut : intérêts encaissés (P&L) face aux
  // intérêts projetés bruts de fiscalité. Le total reçu (capital + intérêts)
  // n'est jamais comparé à des intérêts.
  const totalInvested = projects.reduce((s, p) => s + p.invested_amount, 0)
  const totalProjectedGross = projects.reduce((s, p) => s + (p.projected_interest_gross ?? 0), 0)
  const totalInterestEarned = projects.reduce((s, p) => s + (p.interest_earned ?? 0), 0)
  const onTrackCount = projects.filter((p) => p.on_track && p.status === 'active').length
  const activeCount = projects.filter((p) => p.status === 'active').length

  // XIRR moyen pondéré par le montant investi (projets avec XIRR calculable
  // uniquement), face au taux contractuel moyen pondéré sur le même périmètre.
  const xirrProjects = projects.filter((p) => p.realized_xirr !== null)
  const xirrWeight = xirrProjects.reduce((s, p) => s + p.invested_amount, 0)
  const weightedXirr =
    xirrWeight > 0
      ? xirrProjects.reduce((s, p) => s + p.invested_amount * (p.realized_xirr ?? 0), 0) /
        xirrWeight
      : null
  const weightedContractualRate =
    totalInvested > 0
      ? projects.reduce((s, p) => s + p.invested_amount * p.annual_rate, 0) / totalInvested
      : null

  // Chart data — intérêts perçus vs projetés, tous deux BRUTS
  const chartData = projects
    .filter((p) => p.status !== 'completed')
    .map((p) => ({
      name: (p.project_name || p.platform).substring(0, 20),
      'Intérêts projetés (bruts)': p.projected_interest_gross ?? 0,
      'Intérêts perçus': p.interest_earned ?? 0,
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
      <SpotlightGroup className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          className="spot-card"
          label="XIRR moyen pondéré"
          tooltip="Rendement annualisé des flux réellement encaissés, CRD en valeur terminale ; les retards le dégradent. Pondéré par les montants investis (projets avec XIRR calculable)."
          icon={Percent}
          value={weightedXirr}
          format={formatPercent}
          hint={
            weightedContractualRate !== null ? (
              <>vs taux contractuel moyen {formatPercent(weightedContractualRate)}</>
            ) : undefined
          }
        />
        <StatCard
          className="spot-card"
          label="Intérêts Projetés (bruts)"
          icon={TrendingUp}
          value={totalProjectedGross}
          format={formatCurrency}
          hint={<>bruts de fiscalité · sur {formatCurrency(totalInvested)} investis</>}
        />
        <StatCard
          className="spot-card"
          label="Intérêts encaissés"
          tooltip="Seuls les intérêts sont du P&L — le capital remboursé (retour de principal) n'est pas compté ici."
          icon={CheckCircle2}
          value={totalInterestEarned}
          format={formatCurrency}
          hint={
            totalProjectedGross > 0
              ? `${((totalInterestEarned / totalProjectedGross) * 100).toFixed(0)}% des intérêts projetés (bruts)`
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
            <CardTitle>Intérêts Projetés vs Perçus par Projet</CardTitle>
            <p className="text-xs text-muted-foreground">montants bruts de fiscalité</p>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveBar
                data={chartData}
                keys={['Intérêts projetés (bruts)', 'Intérêts perçus']}
                indexBy="name"
                groupMode="grouped"
                theme={theme}
                margin={{ top: 28, right: 16, bottom: 40, left: 56 }}
                padding={0.25}
                innerPadding={4}
                colors={({ id }) =>
                  id === 'Intérêts projetés (bruts)' ? color('--primary', 0.3) : color('--chart-3')
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
                  <th scope="col" className="pb-2 font-medium text-right">XIRR réalisé</th>
                  <th scope="col" className="pb-2 font-medium text-right">Écart vs contractuel</th>
                  <th scope="col" className="pb-2 font-medium text-right">Projeté (brut)</th>
                  <th scope="col" className="pb-2 font-medium text-right">Intérêts perçus (bruts)</th>
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
                    <td className="py-3 text-right tabular-nums">
                      {p.realized_xirr !== null ? (
                        formatPercent(p.realized_xirr)
                      ) : (
                        <XirrUnavailable />
                      )}
                    </td>
                    <td className="py-3 text-right tabular-nums">
                      {p.xirr_gap !== null ? (
                        <span className={gapColorClass(p.xirr_gap)}>
                          {formatGapPts(p.xirr_gap)}
                        </span>
                      ) : (
                        <XirrUnavailable />
                      )}
                    </td>
                    <td className="py-3 text-right text-gain">
                      {formatCurrency(p.projected_interest_gross ?? 0)}
                    </td>
                    <td className="py-3 text-right">{formatCurrency(p.interest_earned ?? 0)}</td>
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
