import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import {
  Landmark,
  TrendingUp,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ArrowRight,
  RefreshCw,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import type { CrowdfundingDashboard } from '@/types/crowdfunding'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

export default function CrowdfundingDashboardPage() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery<CrowdfundingDashboard>({
    queryKey: queryKeys.crowdfunding.dashboard,
    queryFn: crowdfundingApi.getDashboard,
  })

  const syncCalendar = useMutation({
    mutationFn: crowdfundingApi.syncCalendar,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const d = data

  if (!d || (d.active_count === 0 && d.completed_count === 0)) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Crowdfunding</h1>
          <p className="text-muted-foreground">
            Gérez vos investissements en crowdfunding immobilier et PME
          </p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Landmark className="h-16 w-16 text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold mb-2">Aucun projet</h2>
            <p className="text-muted-foreground mb-6 text-center max-w-md">
              Commencez par ajouter vos investissements en crowdfunding pour suivre
              leur performance et les intégrer à votre patrimoine global.
            </p>
            <Button asChild>
              <Link to="/crowdfunding/projects">
                Ajouter un projet
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const platformData = Object.entries(d.platform_breakdown).map(([name, value]) => ({
    name,
    value,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Crowdfunding</h1>
          <p className="text-muted-foreground">
            Vue d'ensemble de vos investissements crowdfunding
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => syncCalendar.mutate()}
            disabled={syncCalendar.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${syncCalendar.isPending ? 'animate-spin' : ''}`} />
            {syncCalendar.isPending ? 'Synchronisation…' : 'Sync Calendrier'}
          </Button>
          <Button asChild>
            <Link to="/crowdfunding/projects">Mes Projets</Link>
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Investi</CardTitle>
            <Landmark className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(d.total_invested)}</div>
            <p className="text-xs text-muted-foreground">
              sur {d.active_count + d.completed_count + d.delayed_count + d.defaulted_count + d.funding_count} projet(s)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Rendement Projeté / an</CardTitle>
            <TrendingUp className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">
              {formatCurrency(d.projected_annual_interest)}
            </div>
            <p className="text-xs text-muted-foreground">
              Taux moyen pondéré : {d.weighted_average_rate.toFixed(1)}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Reçu</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(d.total_received)}</div>
            <p className="text-xs text-muted-foreground">
              intérêts + remboursements
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Prochaine Échéance</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {d.next_maturity
                ? new Date(d.next_maturity).toLocaleDateString('fr-FR', {
                    month: 'short',
                    year: 'numeric',
                  })
                : '—'}
            </div>
            <p className="text-xs text-muted-foreground">
              {d.delayed_count > 0 && (
                <span className="text-orange-500">
                  {d.delayed_count} projet(s) en retard
                </span>
              )}
              {d.delayed_count === 0 && 'Tous les projets sont à jour'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Platform Breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Répartition par Plateforme</CardTitle>
          </CardHeader>
          <CardContent>
            {platformData.length > 0 ? (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width="50%" height={200}>
                  <PieChart>
                    <Pie
                      data={platformData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      strokeWidth={2}
                    >
                      {platformData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => formatCurrency(v)} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-2">
                  {platformData.map((p, i) => (
                    <div key={p.name} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: COLORS[i % COLORS.length] }}
                        />
                        {p.name}
                      </div>
                      <span className="font-medium">{formatCurrency(p.value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-8">Aucune donnée</p>
            )}
          </CardContent>
        </Card>

        {/* Status Overview */}
        <Card>
          <CardHeader>
            <CardTitle>Statut des Projets</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { label: 'Actifs', count: d.active_count, color: 'bg-green-500', icon: TrendingUp },
              { label: 'Terminés', count: d.completed_count, color: 'bg-blue-500', icon: CheckCircle2 },
              { label: 'En retard', count: d.delayed_count, color: 'bg-orange-500', icon: AlertTriangle },
              { label: 'Défaut', count: d.defaulted_count, color: 'bg-red-500', icon: AlertTriangle },
            ]
              .filter((s) => s.count > 0)
              .map((s) => (
                <div key={s.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`h-2 w-2 rounded-full ${s.color}`} />
                    <span className="text-sm">{s.label}</span>
                  </div>
                  <Badge variant="secondary">{s.count}</Badge>
                </div>
              ))}
          </CardContent>
        </Card>
      </div>

      {/* Recent Projects */}
      {d.projects.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Projets Récents</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/crowdfunding/projects">Voir tout</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {d.projects.slice(0, 5).map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between border-b border-border pb-3 last:border-0 last:pb-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {p.project_name || p.platform}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {p.platform} · {p.annual_rate}% · {p.duration_months} mois
                    </p>
                  </div>
                  <div className="text-right ml-4">
                    <p className="text-sm font-medium">{formatCurrency(p.invested_amount)}</p>
                    <Badge
                      variant={
                        p.status === 'active'
                          ? 'default'
                          : p.status === 'completed'
                            ? 'secondary'
                            : 'destructive'
                      }
                      className="text-xs"
                    >
                      {p.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
