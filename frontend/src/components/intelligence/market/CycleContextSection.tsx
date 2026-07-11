import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { FearGreedGauge } from '@/components/predictions/PredictionMetricCard'
import PredictionCyclesTab from '@/components/predictions/PredictionCyclesTab'
import type { usePredictionData } from '@/hooks/usePredictionData'
import type { UnifiedAlert } from '@/types/predictions'
import {
  AlertTriangle,
  Bell,
  Brain,
  Globe,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'
import PostureSuggestionCard from './PostureSuggestionCard'

/**
 * Section « Cycle & contexte » du pilier Marché & Signaux.
 *
 * Reprend l'onglet Cycles de l'ancienne page Prédictions (phase du cycle
 * détaillée, indicateurs techniques, régimes par actif, top/bottom,
 * time-to-pivot) + le sentiment de marché, les signaux unifiés et les
 * événements de marché à venir. Les grandes bannières de régime prescriptives
 * ont été remplacées par la carte compacte « Suggestion de posture » —
 * le régime lui-même vit dans RegimeHeader (partagé).
 */

// ── Événements de marché à venir ─────────────────────────────────────

interface MarketEvent {
  title: string
  date: string
  category: string
  description: string
  impact: string
  days_until: number
}

function MarketEventsCard() {
  const { data: events } = useQuery<MarketEvent[]>({
    queryKey: queryKeys.predictions.marketEvents,
    queryFn: predictionsApi.getMarketEvents,
    staleTime: 10 * 60 * 1000,
    meta: { suppressGlobalError: true },
  })

  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          <Globe className="h-4 w-4 text-accent" />
          Événements de marché à venir
        </CardTitle>
        <CardDescription>Échéances crypto, macro et fiscales susceptibles d'influencer le marché</CardDescription>
      </CardHeader>
      <CardContent>
        {events && events.length > 0 ? (
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-muted" />
            <div className="space-y-4">
              {events.slice(0, 6).map((event, i) => {
                const dotColor = event.category === 'fiscal' ? 'bg-warning' : 'bg-accent'
                const textColor = event.category === 'fiscal' ? 'text-warning' : 'text-accent'
                return (
                  <div key={i} className="relative flex items-start gap-4 pl-10">
                    <div className={`absolute left-2.5 top-1.5 w-3 h-3 rounded-full ${dotColor} ring-2 ring-background`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm">{event.title}</span>
                        <Badge variant="outline" className={`text-xs ${textColor}`}>
                          {event.category}
                        </Badge>
                        {event.impact === 'high' && (
                          <Badge variant="destructive" className="text-xs">Impact fort</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{event.description}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(event.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })}
                        {' '}· dans {event.days_until} jour{event.days_until > 1 ? 's' : ''}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-6">
            Aucun événement de marché à venir
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Signaux & alertes unifiés ────────────────────────────────────────

function getAlertIcon(icon: string) {
  switch (icon) {
    case 'shield': return <ShieldAlert className="h-5 w-5" />
    case 'trending_up': return <TrendingUp className="h-5 w-5" />
    case 'trending_down': return <TrendingDown className="h-5 w-5" />
    case 'zap': return <Zap className="h-5 w-5" />
    default: return <AlertTriangle className="h-5 w-5" />
  }
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  support_break: 'cassure support',
  breakout: 'cassure résistance',
  strong_trend: 'tendance forte',
  opportunity: 'opportunité',
  info: 'information',
  buy: 'achat',
  sell: 'vente',
}

function UnifiedAlertsCard({ alerts }: { alerts: UnifiedAlert[] }) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-warning" />
          Signaux de marché
        </CardTitle>
        <CardDescription>Alertes prédictives et signaux de sentiment combinés</CardDescription>
      </CardHeader>
      <CardContent>
        {alerts.length > 0 ? (
          <div className="space-y-3">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className={`p-4 rounded-lg border flex items-start gap-3 ${
                  alert.severity === 'high' ? 'bg-loss/10 border-loss/20' :
                  alert.severity === 'medium' ? 'bg-warning/10 border-warning/20' :
                  'bg-gain/10 border-gain/20'
                }`}
              >
                <div className={
                  alert.severity === 'high' ? 'text-loss' :
                  alert.severity === 'medium' ? 'text-warning' : 'text-gain'
                }>
                  {getAlertIcon(alert.icon)}
                </div>
                <div className="flex-1">
                  <p className="font-medium text-sm">{alert.message}</p>
                  <div className="flex items-center gap-2 mt-1">
                    {alert.symbol && <Badge variant="outline" className="text-xs">{alert.symbol}</Badge>}
                    <span className="text-xs text-muted-foreground capitalize">
                      {ALERT_TYPE_LABELS[alert.type] || alert.type.replace('_', ' ')}
                    </span>
                    <span className="text-xs text-muted-foreground">·</span>
                    <span className="text-xs text-muted-foreground">
                      {alert.source === 'signal' ? 'Signal marché' : 'Prédiction'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-muted-foreground py-8">Aucun signal détecté</p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Section principale ───────────────────────────────────────────────

interface CycleContextSectionProps {
  pd: ReturnType<typeof usePredictionData>
}

export default function CycleContextSection({ pd }: CycleContextSectionProps) {
  const {
    marketCycle, loadingCycle,
    sentiment, sentimentError,
    dt, unifiedAlerts, totalAlerts, highAlerts,
  } = pd

  return (
    <div className="space-y-4">
      {/* Suggestion de posture compacte (ex-bannières de régime) */}
      <PostureSuggestionCard marketCycle={marketCycle} />

      {/* Sentiment + événements */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card elevation="raised">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-primary" />
                <span className="font-semibold">Sentiment marché</span>
              </div>
              {totalAlerts > 0 && (
                <Badge variant={highAlerts > 0 ? 'destructive' : 'secondary'} className="text-xs">
                  <Bell className="h-3 w-3 mr-1" />
                  {totalAlerts} {totalAlerts > 1 ? 'signaux' : 'signal'}
                </Badge>
              )}
            </div>
            {sentimentError ? (
              <p className="text-center text-sm text-muted-foreground py-4">Impossible de charger le sentiment</p>
            ) : (
              <>
                <div className="flex items-center justify-center">
                  <FearGreedGauge value={sentiment?.fear_greed_index ?? 50} thresholds={dt.fear_greed} />
                </div>
                <div className="flex items-center justify-center gap-3 mt-3">
                  <Badge variant={
                    sentiment?.overall_sentiment === 'bullish' ? 'default' :
                    sentiment?.overall_sentiment === 'bearish' ? 'destructive' : 'secondary'
                  }>
                    {sentiment?.overall_sentiment === 'bullish' ? 'Haussier' :
                     sentiment?.overall_sentiment === 'bearish' ? 'Baissier' :
                     sentiment?.overall_sentiment === 'neutral' ? 'Neutre' :
                     sentiment?.overall_sentiment ?? 'N/A'}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {{ markup: 'Expansion', markdown: 'Contraction', accumulation: 'Accumulation', distribution: 'Distribution' }[sentiment?.market_phase ?? ''] ?? sentiment?.market_phase ?? ''}
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <MarketEventsCard />
      </div>

      {/* Phase du cycle détaillée, indicateurs techniques, régimes par actif,
          estimations top/bottom, time-to-pivot, conseils de cycle */}
      <PredictionCyclesTab marketCycle={marketCycle} loadingCycle={loadingCycle} />

      {/* Signaux de marché unifiés */}
      <UnifiedAlertsCard alerts={unifiedAlerts} />
    </div>
  )
}
