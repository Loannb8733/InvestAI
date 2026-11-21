import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { Flame, GitBranch } from 'lucide-react'
import type { AnomalyImpact, MetricsSummary } from '../types'

interface SmartRiskCardsProps {
  metrics: MetricsSummary
  anomalyImpacts: AnomalyImpact[]
}

export default function SmartRiskCards({ metrics, anomalyImpacts }: SmartRiskCardsProps) {
  const clusters = metrics.risk_clusters ?? []
  const hasClusters = clusters.length > 0
  const hasAnomalies = anomalyImpacts.length > 0

  if (!hasClusters && !hasAnomalies) return null

  const totalFlashImpact = anomalyImpacts.reduce(
    (sum, a) => sum + (a.impact_eur < 0 ? a.impact_eur : 0), 0
  )
  const totalValue = metrics.total_value || 1
  const flashPct = (totalFlashImpact / totalValue) * 100

  return (
    <div className="grid gap-4 lg:grid-cols-2 items-start">

      {hasClusters && (
        <Card elevation="raised" className="border-loss/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-5 w-5 text-loss" />
              Clusters de Risque
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {clusters.map((cluster, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-loss/5 border border-loss/10">
                  <div className="flex items-center gap-2 flex-wrap">
                    {cluster.assets.map((asset) => (
                      <Badge key={asset} variant="outline" className="border-loss/30 text-loss">
                        {asset}
                      </Badge>
                    ))}
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-loss">{(cluster.avg_corr * 100).toFixed(0)}%</p>
                    <p className="text-[10px] text-muted-foreground">corrélation</p>
                  </div>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                Ces actifs bougent ensemble (corrélation &gt; 85%). En cas de chute, ils baisseront
                simultanément. La matrice de corrélation complète est affichée plus bas dans ce pilier.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {hasAnomalies && (
        <Card elevation="raised" className="border-warning/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Flame className="h-5 w-5 text-warning" />
              Impact Flash Crash
            </CardTitle>
            <CardDescription>
              Simulation de perte immédiate basée sur les anomalies détectées
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm text-muted-foreground">Perte simulée</p>
                <p className="text-3xl font-serif font-medium text-loss">
                  {formatCurrency(Math.abs(totalFlashImpact))}
                </p>
                <p className="text-xs text-muted-foreground">
                  soit {Math.abs(flashPct).toFixed(1)}% de {formatCurrency(totalValue)}
                </p>
              </div>
              <div className={`h-16 w-16 rounded-full flex items-center justify-center ${
                Math.abs(flashPct) > 10 ? 'bg-loss/10' : Math.abs(flashPct) > 5 ? 'bg-warning/10' : 'bg-warning/10'
              }`}>
                <Flame className={`h-8 w-8 ${
                  Math.abs(flashPct) > 10 ? 'text-loss' : Math.abs(flashPct) > 5 ? 'text-warning' : 'text-warning'
                }`} />
              </div>
            </div>
            <div className="space-y-2">
              {anomalyImpacts.filter((a) => a.impact_eur < 0).map((anomaly, idx) => (
                <div key={idx} className="flex items-center justify-between text-sm p-2 rounded bg-muted/50">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{anomaly.symbol}</span>
                    <Badge variant="outline" className="text-xs">{anomaly.anomaly_type}</Badge>
                  </div>
                  <span className="font-mono text-loss">{formatCurrency(anomaly.impact_eur)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

    </div>
  )
}
