import { Activity, BarChart3, Info } from 'lucide-react'
import EmptyState from '@/components/ui/empty-state'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import { downloadAnalyticsCsv } from '../csv'
import { useRiskPillar } from '../useRiskPillar'
import AllocationRiskCharts from './AllocationRiskCharts'
import { BetaCard, DiversificationRecommendations, TopWorstPerformers } from './AnalyticsExtras'
import CorrelationMatrix from './CorrelationMatrix'
import HealthScoreSection from './HealthScoreSection'
import OptimizationSection from './OptimizationSection'
import PerformanceCharts from './PerformanceCharts'
import PortfolioEvolutionChart from './PortfolioEvolutionChart'
import ProjectionRow from './ProjectionRow'
import RiskMetricRows from './RiskMetricRows'
import ScopeToolbar from './ScopeToolbar'
import SmartRiskCards from './SmartRiskCards'

function PillarSkeleton() {
  return (
    <div className="space-y-6">
      {[0, 1].map((row) => (
        <div key={row} className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
      ))}
    </div>
  )
}

export default function RiskPerformancePillar() {
  const pillar = useRiskPillar()
  const { analytics, diversification, health, beta, mode } = pillar

  if (analytics.isLoading || diversification.isLoading) return <PillarSkeleton />
  if (analytics.isError) {
    return (
      <EmptyState
        variant="error"
        icon={Activity}
        title="Erreur de chargement"
        description="Impossible de charger les analyses de risque. Veuillez réessayer."
      />
    )
  }
  if (!analytics.data || analytics.data.asset_count === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Aucune donnée à analyser"
        description="Ajoutez des actifs à vos portefeuilles pour voir le risque et la performance."
      />
    )
  }

  const data = analytics.data
  const betaData = beta.data && beta.data.assets.length > 0 ? beta.data : undefined
  const advice = diversification.data && diversification.data.recommendations.length > 0 ? diversification.data : undefined

  return (
    <div className="space-y-6">
      <ScopeToolbar
        scope={pillar.scope}
        onExport={() => downloadAnalyticsCsv(data.assets)}
        onRefresh={() => health.refetch()}
        refreshing={health.isFetching}
      />
      <HealthScoreSection
        health={health.data}
        isLoading={health.isLoading}
        isError={health.isError}
        onRetry={() => health.refetch()}
        days={pillar.scope.days}
        isBearMode={mode.isBearMode}
        isBullMode={mode.isBullMode}
      />
      {data.interpretations?.global && (
        <div className="flex items-center gap-2 rounded-lg border border-warning dark:border-warning bg-warning dark:bg-warning/20 p-3">
          <Info className="h-4 w-4 text-warning shrink-0" />
          <p className="text-sm text-warning dark:text-warning">{data.interpretations.global}</p>
        </div>
      )}
      <RiskMetricRows analytics={data} diversification={diversification.data} xirr={pillar.xirr.data?.xirr} />
      {health.data && <SmartRiskCards metrics={health.data.metrics_summary} anomalyImpacts={health.data.anomaly_impacts} />}
      <OptimizationSection
        optimization={pillar.optimization.data}
        allocationByAsset={data.allocation_by_asset}
        assetCount={data.asset_count}
        objective={pillar.objective}
        onObjectiveChange={pillar.changeObjective}
        rebalance={pillar.rebalance}
        mptOrders={health.data?.rebalancing_orders ?? []}
        plannedSymbols={pillar.plannedSymbols}
        onPlanOrder={(order) => pillar.planOrder.mutate(order)}
        isPlanningOrder={pillar.planOrder.isPending}
        mode={mode}
      />
      <PortfolioEvolutionChart chartHistoricalData={pillar.evolution} />
      <AllocationRiskCharts analytics={data} diversificationScore={diversification.data?.score || 0} />
      <ProjectionRow
        monteCarlo={pillar.monteCarlo.data}
        stressTest={pillar.stressTest.data}
        horizon={pillar.horizon}
        onHorizonChange={pillar.setHorizon}
      />
      {(betaData || advice) && (
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          {betaData && <BetaCard betaData={betaData} betaDays={pillar.windowDays} periodDays={pillar.scope.days} />}
          {diversification.data && <DiversificationRecommendations diversification={diversification.data} />}
        </div>
      )}
      <PerformanceCharts analytics={data} />
      {pillar.correlation.data && pillar.correlation.data.symbols.length > 1 && (
        <CorrelationMatrix correlation={pillar.correlation.data} days={pillar.scope.days} />
      )}
      {pillar.performance.data && <TopWorstPerformers performance={pillar.performance.data} />}
      {health.data && (
        <p className="text-xs text-muted-foreground text-center">
          Analyse de santé générée le {new Date(health.data.generated_at).toLocaleString('fr-FR')}
        </p>
      )}
    </div>
  )
}
