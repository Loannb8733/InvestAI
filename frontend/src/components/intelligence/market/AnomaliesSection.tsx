import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/empty-state'
import { formatCurrency } from '@/lib/utils'
import { smartInsightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { AlertTriangle, CheckCircle2, Flame } from 'lucide-react'

/**
 * Section « Anomalies » du pilier Marché & Signaux.
 *
 * Source unique retenue : /smart-insights/anomalies-impact (Smart Insights),
 * plus complète que /predictions/anomalies — chaque anomalie y est chiffrée
 * en EUR (impact sur la position, valeur de la position), là où la version
 * Prédictions ne donnait que le % de variation. On agrège aussi l'impact
 * « flash crash » total, comme le faisait SmartInsightsPage.
 */

interface AnomalyImpact {
  symbol: string
  anomaly_type: string
  severity: string
  description: string
  price_change_percent: number
  position_value_eur: number
  impact_eur: number
  detected_at: string
}

export default function AnomaliesSection() {
  const { data: anomalies, isLoading, isError } = useQuery<AnomalyImpact[]>({
    queryKey: queryKeys.smartInsights.anomaliesImpact,
    queryFn: smartInsightsApi.getAnomaliesImpact,
    staleTime: 5 * 60 * 1000,
    meta: { suppressGlobalError: true },
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-72 mt-1" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  if (isError) {
    return (
      <Card className="border-warning/20">
        <CardContent className="py-6 text-center">
          <AlertTriangle className="h-8 w-8 mx-auto text-warning mb-2" />
          <p className="text-sm text-muted-foreground">Impossible de charger les anomalies</p>
        </CardContent>
      </Card>
    )
  }

  if (!anomalies || anomalies.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Aucune anomalie détectée"
        description="Aucun mouvement inhabituel sur vos positions pour le moment."
      />
    )
  }

  const totalNegativeImpact = anomalies.reduce(
    (sum, a) => sum + (a.impact_eur < 0 ? a.impact_eur : 0),
    0
  )

  return (
    <div className="space-y-4">
      {/* Impact agrégé (ex-carte « Impact Flash Crash ») */}
      {totalNegativeImpact < 0 && (
        <Card elevation="raised" className="border-warning/20">
          <CardContent className="pt-4 flex items-center gap-3">
            <Flame className="h-6 w-6 text-warning shrink-0" />
            <div>
              <p className="text-sm text-muted-foreground">Impact cumulé des anomalies négatives</p>
              <p className="text-2xl font-serif font-medium text-loss tabular-nums">
                {formatCurrency(totalNegativeImpact)}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card elevation="raised" className="border-warning/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-warning" />
            Anomalies détectées
          </CardTitle>
          <CardDescription>
            Mouvements inhabituels sur vos positions avec impact en EUR
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {anomalies.map((anomaly, idx) => (
              <div key={idx} className="p-4 rounded-lg bg-muted/50 border">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{anomaly.symbol}</span>
                    <Badge variant="outline" className={
                      anomaly.severity === 'high' ? 'border-loss text-loss' :
                      anomaly.severity === 'medium' ? 'border-warning text-warning' :
                      'border-accent text-accent'
                    }>
                      {anomaly.severity}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      {anomaly.anomaly_type}
                    </Badge>
                  </div>
                  <div className="text-right">
                    <div className={`font-mono font-bold ${(anomaly.impact_eur ?? 0) >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {(anomaly.impact_eur ?? 0) >= 0 ? '+' : ''}{formatCurrency(anomaly.impact_eur ?? 0)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {(anomaly.price_change_percent ?? 0) >= 0 ? '+' : ''}{(anomaly.price_change_percent ?? 0).toFixed(1)}%
                    </div>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Position : {formatCurrency(anomaly.position_value_eur ?? 0)} |
                  Détecté : {new Date(anomaly.detected_at).toLocaleDateString('fr-FR')}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
