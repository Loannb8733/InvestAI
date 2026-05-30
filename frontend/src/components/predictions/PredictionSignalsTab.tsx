import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Anomaly, UnifiedAlert } from '@/types/predictions'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Zap,
  ShieldAlert,
} from 'lucide-react'

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

interface PredictionSignalsTabProps {
  unifiedAlerts: UnifiedAlert[]
  anomalies?: Anomaly[]
  anomaliesError: boolean
}

export default function PredictionSignalsTab({ unifiedAlerts, anomalies, anomaliesError }: PredictionSignalsTabProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-warning" />
            Signaux & alertes
          </CardTitle>
          <CardDescription>Alertes prédictives et signaux de marché combinés</CardDescription>
        </CardHeader>
        <CardContent>
          {unifiedAlerts.length > 0 ? (
            <div className="space-y-3">
              {unifiedAlerts.map((alert, i) => (
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
                      <span className="text-xs text-muted-foreground">{alert.source === 'signal' ? 'Signal marché' : 'Prédiction'}</span>
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

      {/* Anomalies */}
      {anomaliesError && (
        <Card className="border-warning/20">
          <CardContent className="py-6 text-center">
            <AlertTriangle className="h-8 w-8 mx-auto text-warning mb-2" />
            <p className="text-sm text-muted-foreground">Impossible de charger les anomalies</p>
          </CardContent>
        </Card>
      )}
      {anomalies && anomalies.filter(a => a.is_anomaly).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-warning" />
              Anomalies détectées
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {anomalies.filter(a => a.is_anomaly).map((anomaly, index) => (
                <div
                  key={index}
                  className={`p-4 rounded-lg border ${
                    anomaly.severity === 'high' ? 'bg-loss/10 border-loss/20' :
                    anomaly.severity === 'medium' ? 'bg-warning/10 border-warning/20' :
                    'bg-accent/10 border-accent/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{anomaly.symbol}</span>
                      <Badge variant={anomaly.severity === 'high' ? 'destructive' : 'secondary'}>
                        {anomaly.anomaly_type}
                      </Badge>
                    </div>
                    <span className={`font-medium ${anomaly.price_change_percent >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {anomaly.price_change_percent >= 0 ? '+' : ''}{anomaly.price_change_percent.toFixed(2)}%
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
