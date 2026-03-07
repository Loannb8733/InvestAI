import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { Loader2, TrendingUp, AlertTriangle, CheckCircle2 } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { CrowdfundingPerformanceItem } from '@/types/crowdfunding'

export default function CrowdfundingPerformancePage() {
  const { data, isLoading } = useQuery<{ projects: CrowdfundingPerformanceItem[] }>({
    queryKey: queryKeys.crowdfunding.performance,
    queryFn: crowdfundingApi.getPerformance,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const projects = data?.projects || []

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Performance Crowdfunding</h1>
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
        <h1 className="text-3xl font-bold">Performance Crowdfunding</h1>
        <p className="text-muted-foreground">
          Suivi des rendements projetés vs réalisés
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Intérêts Projetés (Total)</CardTitle>
            <TrendingUp className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">
              {formatCurrency(totalProjectedInterest)}
            </div>
            <p className="text-xs text-muted-foreground">
              sur {formatCurrency(totalInvested)} investis
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Reçu</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totalReceived)}</div>
            <p className="text-xs text-muted-foreground">
              {totalProjectedInterest > 0
                ? `${((totalReceived / totalProjectedInterest) * 100).toFixed(0)}% des intérêts projetés`
                : '—'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Projets On Track</CardTitle>
            {onTrackCount === activeCount ? (
              <CheckCircle2 className="h-4 w-4 text-green-500" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-orange-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {onTrackCount}/{activeCount}
            </div>
            <p className="text-xs text-muted-foreground">
              {onTrackCount === activeCount
                ? 'Tous les projets actifs sont à jour'
                : `${activeCount - onTrackCount} projet(s) en retard`}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart: Projected vs Received */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Projeté vs Reçu par Projet</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12 }}
                  stroke="hsl(var(--muted-foreground))"
                />
                <YAxis
                  tickFormatter={(v) => `${v}€`}
                  stroke="hsl(var(--muted-foreground))"
                />
                <Tooltip
                  formatter={(v: number) => formatCurrency(v)}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Legend />
                <Bar
                  dataKey="Intérêts projetés"
                  fill="hsl(var(--primary))"
                  radius={[4, 4, 0, 0]}
                  opacity={0.3}
                />
                <Bar
                  dataKey="Reçu"
                  fill="#10b981"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Detail table */}
      <Card>
        <CardHeader>
          <CardTitle>Détail par Projet</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 font-medium">Projet</th>
                  <th className="pb-2 font-medium">Plateforme</th>
                  <th className="pb-2 font-medium text-right">Investi</th>
                  <th className="pb-2 font-medium text-right">Taux</th>
                  <th className="pb-2 font-medium text-right">Projeté</th>
                  <th className="pb-2 font-medium text-right">Reçu</th>
                  <th className="pb-2 font-medium text-center">Progression</th>
                  <th className="pb-2 font-medium text-center">Statut</th>
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
                    <td className="py-3 text-right text-green-500">
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
                        <Badge variant="secondary" className="bg-green-500/10 text-green-500">
                          OK
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-orange-500/10 text-orange-500">
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
