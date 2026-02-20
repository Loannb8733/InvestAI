import { Card, CardContent } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import {
  Activity,
  Zap,
  TrendingDown as TrendDown,
  ShieldAlert,
  Info,
} from 'lucide-react'

function MetricTooltip({ children, content }: { children: React.ReactNode; content: string }) {
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help inline-flex items-center gap-1">
            {children}
            <Info className="h-3 w-3 text-muted-foreground" />
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-sm">{content}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

interface MaxDrawdown {
  max_drawdown_percent: number
  peak_date?: string
  trough_date?: string
  peak_value?: number
  trough_value?: number
}

interface ValueAtRisk {
  var_percent: number
  var_amount: number
  confidence_level: number
}

interface RiskMetrics {
  volatility: number
  sharpe_ratio: number
  max_drawdown: MaxDrawdown
  var_95: ValueAtRisk
  beta?: number
  alpha?: number
}

interface DashboardRiskCardsProps {
  riskMetrics: RiskMetrics
}

export default function DashboardRiskCards({ riskMetrics }: DashboardRiskCardsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <MetricTooltip content="Mesure de la dispersion des rendements. Plus la volatilité est élevée, plus le risque est important."><p className="text-sm text-muted-foreground">Volatilité</p></MetricTooltip>
              <p className="text-xl font-bold">{riskMetrics.volatility.toFixed(1)}%</p>
              <p className="text-xs text-muted-foreground">annualisée</p>
            </div>
            <Activity className="h-8 w-8 text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <MetricTooltip content="Rendement ajusté au risque. >1 = bon, >2 = très bon, <0 = mauvais"><p className="text-sm text-muted-foreground">Ratio de Sharpe</p></MetricTooltip>
              <p className={`text-xl font-bold ${riskMetrics.sharpe_ratio >= 1 ? 'text-green-500' : riskMetrics.sharpe_ratio >= 0 ? 'text-yellow-500' : 'text-red-500'}`}>{riskMetrics.sharpe_ratio.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">{riskMetrics.sharpe_ratio >= 1 ? 'Bon' : riskMetrics.sharpe_ratio >= 0 ? 'Moyen' : 'Faible'}</p>
            </div>
            <Zap className="h-8 w-8 text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <MetricTooltip content="Perte maximale historique entre un pic et un creux. Mesure le pire scénario passé."><p className="text-sm text-muted-foreground">Max Drawdown</p></MetricTooltip>
              <p className="text-xl font-bold text-red-500">-{riskMetrics.max_drawdown.max_drawdown_percent.toFixed(1)}%</p>
              <p className="text-xs text-muted-foreground">pire baisse</p>
            </div>
            <TrendDown className="h-8 w-8 text-red-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <MetricTooltip content={`Perte potentielle maximale avec ${(riskMetrics.var_95.confidence_level * 100).toFixed(0)}% de confiance sur 1 jour.`}><p className="text-sm text-muted-foreground">VaR 95%</p></MetricTooltip>
              <p className="text-xl font-bold text-orange-500">{formatCurrency(riskMetrics.var_95.var_amount)}</p>
              <p className="text-xs text-muted-foreground">soit {riskMetrics.var_95.var_percent.toFixed(1)}%</p>
            </div>
            <ShieldAlert className="h-8 w-8 text-orange-500" />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
