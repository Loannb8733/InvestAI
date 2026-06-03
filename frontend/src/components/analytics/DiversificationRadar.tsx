import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, CheckCircle2, Globe, Building2, TrendingUp } from 'lucide-react'
import { ResponsiveRadar } from '@nivo/radar'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { ProjectAudit } from '@/types/crowdfunding'

const IMPACT_CONFIG = {
  ameliore: { label: 'Améliore la diversification', color: 'bg-gain', icon: CheckCircle2 },
  neutre: { label: 'Impact neutre', color: 'bg-warning', icon: AlertTriangle },
  degrade: { label: 'Dégrade la diversification', color: 'bg-loss', icon: AlertTriangle },
} as const

interface DiversificationRadarProps {
  audit: ProjectAudit
}

export default function DiversificationRadar({ audit }: DiversificationRadarProps) {
  const { theme, color } = useNivoTheme()
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
            <div className="h-[250px]">
              <ResponsiveRadar
                data={radarData}
                keys={['value']}
                indexBy="axis"
                theme={theme}
                maxValue={100}
                margin={{ top: 28, right: 36, bottom: 28, left: 36 }}
                gridLevels={5}
                gridShape="circular"
                gridLabelOffset={12}
                colors={[color('--chart-4')]}
                fillOpacity={0.2}
                borderWidth={2}
                borderColor={{ from: 'color' }}
                dotSize={6}
                dotColor={color('--chart-4')}
                dotBorderWidth={2}
                dotBorderColor={color('--background')}
                enableDotLabel={false}
                isInteractive
                motionConfig="gentle"
                sliceTooltip={({ index, data }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="text-sm font-medium">{index}</p>
                    <p className="mt-0.5 font-mono text-sm tabular-nums text-muted-foreground">
                      {data[0]?.value}%
                    </p>
                  </div>
                )}
              />
            </div>
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
                          ? 'bg-loss'
                          : correlationPct > 30
                            ? 'bg-warning'
                            : 'bg-gain'
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
                          item.value > 60 ? 'bg-loss' : item.value > 30 ? 'bg-warning' : 'bg-gain'
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
              <div className="bg-warning dark:bg-warning/20 border border-warning dark:border-warning rounded-lg p-3">
                <p className="text-sm text-warning dark:text-warning">
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
