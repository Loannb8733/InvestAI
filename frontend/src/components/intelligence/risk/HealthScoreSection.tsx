import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton, SkeletonStatCard } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/empty-state'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { formatCurrency } from '@/lib/utils'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Gauge,
  RefreshCw,
  Shield,
  TrendingUp,
  Zap,
} from 'lucide-react'
import type { PortfolioHealth } from './types'

/**
 * Tête du pilier « Risque & Performance » : le score de santé décomposé.
 *
 * Copié depuis SmartInsightsPage (score global + Recommandations IA avec
 * potential_improvement). Les cartes métriques dupliquées de SmartInsights
 * (Sharpe, VaR, HHI, Max Drawdown) ne sont PAS reprises ici : la seule
 * source de vérité des métriques de risque est RiskMetricRows (queries
 * Analytics, pilotées par le sélecteur unique du pilier).
 */

function formatMetric(name: string | undefined, value: number): string {
  const v = Number.isFinite(value) ? value : 0
  if (!name) return v.toFixed(2)
  const n = name.toLowerCase()
  if (n.includes('volatil') || n.includes('drawdown') || n.includes('hhi'))
    return `${(v * 100).toFixed(1)}%`
  if (n.includes('var'))
    return formatCurrency(v)
  return v.toFixed(2)
}

const getScoreColor = (score: number) => {
  if (score >= 80) return 'text-gain'
  if (score >= 60) return 'text-warning'
  if (score >= 40) return 'text-warning'
  return 'text-loss'
}

const getScoreBg = (score: number) => {
  if (score >= 80) return 'bg-gain/10 border-gain/20'
  if (score >= 60) return 'bg-warning/10 border-warning/20'
  if (score >= 40) return 'bg-warning/10 border-warning/20'
  return 'bg-loss/10 border-loss/20'
}

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case 'critical': return 'bg-loss/10 text-loss border-loss/20'
    case 'warning': return 'bg-warning/10 text-warning border-warning/20'
    case 'info': return 'bg-accent/10 text-accent border-accent/20'
    default: return 'bg-muted text-muted-foreground'
  }
}

const getCategoryIcon = (category: string) => {
  switch (category) {
    case 'performance': return <TrendingUp className="h-4 w-4" />
    case 'risk': return <Shield className="h-4 w-4" />
    case 'diversification': return <BarChart3 className="h-4 w-4" />
    case 'anomaly': return <AlertTriangle className="h-4 w-4" />
    default: return <Activity className="h-4 w-4" />
  }
}

interface HealthScoreSectionProps {
  health: PortfolioHealth | undefined
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  days: number
  isBearMode: boolean
  isBullMode: boolean
}

export default function HealthScoreSection({
  health,
  isLoading,
  isError,
  onRetry,
  days,
  isBearMode,
  isBullMode,
}: HealthScoreSectionProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        <SkeletonStatCard />
        <Card className="lg:col-span-2">
          <CardHeader>
            <Skeleton className="h-5 w-48" />
          </CardHeader>
          <CardContent className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isError) {
    return (
      <EmptyState
        variant="error"
        icon={AlertTriangle}
        title="Erreur lors du chargement du score de santé"
        action={
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Réessayer
          </Button>
        }
      />
    )
  }

  if (!health) return null

  return (
    <SpotlightGroup className="grid gap-4 lg:grid-cols-3">
      {/* Score global */}
      <Card elevation="raised" className={`spot-card border-2 ${getScoreBg(health.overall_score)}`}>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Score de santé ({days}j)</p>
              <div className={`text-5xl font-serif font-medium ${getScoreColor(health.overall_score)}`}>
                {health.overall_score}
                <span className="text-lg text-muted-foreground font-normal">/100</span>
              </div>
              <p className="text-sm mt-1 capitalize">{health.overall_status}</p>
            </div>
            <Gauge className={`h-16 w-16 ${getScoreColor(health.overall_score)}`} />
          </div>
        </CardContent>
      </Card>

      {/* Décomposition : Recommandations IA (insights avec potential_improvement) */}
      {health.insights.length > 0 ? (
        <Card elevation="raised" className="spot-card lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-warning" />
              Recommandations IA
            </CardTitle>
            <CardDescription>
              Ce qui pèse sur le score — et le gain potentiel de chaque action
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {health.insights.map((insight, idx) => (
                <div key={idx} className={`p-4 rounded-lg border ${getSeverityColor(insight.severity)}`}>
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">{getCategoryIcon(insight.category)}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold">{insight.title}</h4>
                        <Badge variant="outline" className="text-xs capitalize">
                          {insight.category}
                        </Badge>
                      </div>
                      <p className="text-sm">{insight.message}</p>

                      {insight.current_value != null && insight.target_value != null && (
                        <div className="mt-2 flex items-center gap-4 text-sm">
                          <span>Actuel: <strong>{formatMetric(insight.metric_name, insight.current_value)}</strong></span>
                          <ArrowUpRight className="h-4 w-4" />
                          <span>Objectif: <strong>{formatMetric(insight.metric_name, insight.target_value)}</strong></span>
                        </div>
                      )}

                      {insight.potential_improvement && (
                        <p className="mt-2 text-sm text-gain">
                          <CheckCircle2 className="h-4 w-4 inline mr-1" />
                          {insight.potential_improvement}
                        </p>
                      )}

                      {insight.actions.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {insight.actions.map((action, aidx) => (
                            <Badge key={aidx} variant="secondary" className="text-xs" title={
                              action.type === 'buy' && isBearMode ? 'Accumulation — les prix sont décotés' :
                              action.type === 'buy' && isBullMode ? 'Achat modéré — les prix sont élevés' :
                              action.type === 'sell' && isBearMode ? 'Vente différée — éviter de vendre en bear' :
                              action.type === 'sell' && isBullMode ? 'Prise de profits recommandée' :
                              undefined
                            }>
                              {action.type === 'buy' ? (
                                <ArrowUpRight className="h-3 w-3 mr-1 text-gain" />
                              ) : action.type === 'sell' ? (
                                <ArrowDownRight className="h-3 w-3 mr-1 text-loss" />
                              ) : null}
                              {action.type === 'buy' && isBearMode ? 'ACCUMULER' :
                               action.type === 'sell' && isBullMode ? 'PRENDRE PROFITS' :
                               action.type.toUpperCase()} {action.symbol}
                              {action.amount_eur && ` (${formatCurrency(action.amount_eur)})`}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card elevation="raised" className="spot-card lg:col-span-2">
          <CardContent className="pt-6 h-full flex items-center">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="h-8 w-8 text-gain shrink-0" />
              <div>
                <p className="font-medium">Aucune action prioritaire</p>
                <p className="text-sm text-muted-foreground">
                  Le score de santé ne détecte aucun levier d'amélioration majeur sur cette période.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </SpotlightGroup>
  )
}
