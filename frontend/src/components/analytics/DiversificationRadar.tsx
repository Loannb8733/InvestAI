import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, CheckCircle2, Globe, Building2, TrendingUp } from 'lucide-react'
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from 'recharts'
import type { ProjectAudit } from '@/types/crowdfunding'

const IMPACT_CONFIG = {
  ameliore: { label: 'Améliore la diversification', color: 'bg-green-500', icon: CheckCircle2 },
  neutre: { label: 'Impact neutre', color: 'bg-yellow-500', icon: AlertTriangle },
  degrade: { label: 'Dégrade la diversification', color: 'bg-red-500', icon: AlertTriangle },
} as const

interface DiversificationRadarProps {
  audit: ProjectAudit
}

export default function DiversificationRadar({ audit }: DiversificationRadarProps) {
  const { diversification_impact, correlation_score, portfolio_concentration } = audit

  if (!diversification_impact && correlation_score == null) return null

  const impact = diversification_impact as keyof typeof IMPACT_CONFIG
  const config = IMPACT_CONFIG[impact] || IMPACT_CONFIG.neutre
  const Icon = config.icon

  const concentration = portfolio_concentration ?? {}
  const radarData = [
    {
      axis: 'Géographie',
      value: Math.round((concentration.geographic ?? 0) * 100),
      icon: Globe,
    },
    {
      axis: 'Type d\'actif',
      value: Math.round((concentration.asset_type ?? 0) * 100),
      icon: Building2,
    },
    {
      axis: 'Risque/Rendement',
      value: Math.round((concentration.risk_return ?? 0) * 100),
      icon: TrendingUp,
    },
  ]

  const correlationPct = correlation_score != null ? Math.round(correlation_score * 100) : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Diversification vs Portefeuille
          </span>
          <Badge className={`${config.color} text-white`}>
            <Icon className="h-3 w-3 mr-1" />
            {config.label}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Radar */}
          <div>
            <ResponsiveContainer width="100%" height={250}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="axis" className="text-xs" />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={5} />
                <Radar
                  name="Concentration"
                  dataKey="value"
                  stroke="#ef4444"
                  fill="#ef4444"
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
            <p className="text-xs text-center text-muted-foreground mt-1">
              Concentration actuelle par axe (%)
            </p>
          </div>

          {/* Details */}
          <div className="space-y-4">
            {/* Correlation Score */}
            {correlationPct != null && (
              <div>
                <p className="text-sm font-medium mb-2">Score de corrélation</p>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        correlationPct > 60
                          ? 'bg-red-500'
                          : correlationPct > 30
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                      }`}
                      style={{ width: `${correlationPct}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold w-12 text-right">{correlationPct}%</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {correlationPct > 60
                    ? 'Forte corrélation — allocation réduite recommandée'
                    : correlationPct > 30
                      ? 'Corrélation modérée — allocation légèrement ajustée'
                      : 'Faible corrélation — bonne diversification'}
                </p>
              </div>
            )}

            {/* Concentration Breakdown */}
            <div className="space-y-2">
              <p className="text-sm font-medium">Détail par axe</p>
              {radarData.map((item) => {
                const AxisIcon = item.icon
                return (
                  <div key={item.axis} className="flex items-center gap-2">
                    <AxisIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="text-sm w-32">{item.axis}</span>
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          item.value > 60 ? 'bg-red-400' : item.value > 30 ? 'bg-yellow-400' : 'bg-green-400'
                        }`}
                        style={{ width: `${item.value}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-10 text-right">{item.value}%</span>
                  </div>
                )
              })}
            </div>

            {/* Allocation Impact */}
            {audit.suggested_investment != null && impact === 'degrade' && (
              <div className="bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800 rounded-lg p-3">
                <p className="text-sm text-orange-700 dark:text-orange-300">
                  <AlertTriangle className="h-4 w-4 inline mr-1" />
                  L'allocation a été réduite de 5% à ~2% du capital en raison de la forte corrélation
                  avec votre portefeuille existant.
                </p>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
