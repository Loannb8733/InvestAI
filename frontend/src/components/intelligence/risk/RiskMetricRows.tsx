import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { formatCurrency } from '@/lib/utils'
import {
  Activity,
  ArrowDownRight,
  HelpCircle,
  Percent,
  PieChart as PieChartIcon,
  Shield,
  Target,
  TrendingDown,
  Zap,
} from 'lucide-react'
import type { AnalyticsData, Diversification } from './types'

/**
 * Métriques de risque UNIFIÉES du pilier « Risque & Performance ».
 *
 * Source unique : les queries d'Analytics (endpoint /analytics), pilotées par
 * le sélecteur période/portefeuille du pilier. Les cartes équivalentes de
 * SmartInsights (Sharpe, VaR, Max Drawdown, HHI) sont supprimées : fini le
 * Sharpe différent entre deux onglets.
 *
 * Concentration : affichée UNE fois, au format Analytics — le score de
 * diversification /100 (composite nb actifs + nb classes + HHI), plus
 * lisible que le HHI brut ×10000 de SmartInsights.
 */

// Tooltips d'explication des métriques (copiés d'AnalyticsPage)
const metricExplanations: Record<string, { title: string; description: string }> = {
  volatility: {
    title: 'Volatilité',
    description: 'Variation annualisée des prix (σ√252). Crypto: 50-100% normal. Actions: 15-25% typique.',
  },
  sharpe: {
    title: 'Ratio de Sharpe',
    description: 'Rendement excédentaire / volatilité. > 1 = bon, > 2 = excellent, < 0 = rendement sous le taux sans risque.',
  },
  sortino: {
    title: 'Ratio de Sortino',
    description: 'Comme le Sharpe, mais ne pénalise que la volatilité baissière. Plus pertinent car la hausse n\'est pas un risque.',
  },
  calmar: {
    title: 'Ratio de Calmar',
    description: 'Rendement annualisé / max drawdown. Mesure la capacité à se remettre des pertes. > 1 = bon.',
  },
  var: {
    title: 'VaR 95%',
    description: 'Perte max journalière avec 95% de confiance. Basé sur l\'historique réel des rendements.',
  },
  cvar: {
    title: 'CVaR / Expected Shortfall',
    description: 'Perte moyenne quand on dépasse le VaR. Plus conservateur — mesure le risque extrême.',
  },
  diversification: {
    title: 'Score de Diversification',
    description: 'Composite: nb actifs + nb classes + concentration (HHI). 0-40: Faible, 40-60: Moyen, 60-80: Bon, 80+: Excellent.',
  },
  maxdd: {
    title: 'Max Drawdown',
    description: 'Plus grande perte depuis un sommet historique. Mesure le pire scénario vécu.',
  },
  xirr: {
    title: 'XIRR',
    description: 'Taux de rendement interne annualisé. Tient compte du timing de chaque investissement (DCA vs lump sum).',
  },
}

const MetricWithTooltip = ({ metricKey, children }: { metricKey: string; children: React.ReactNode }) => {
  const explanation = metricExplanations[metricKey]
  if (!explanation) return <>{children}</>
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1 cursor-help" aria-label={`Aide sur ${explanation.title}`}>
            {children}
            <HelpCircle className="h-3 w-3 text-muted-foreground" />
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="font-medium">{explanation.title}</p>
          <p className="text-xs text-muted-foreground mt-1">{explanation.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Formatage sûr avec fallback pour null/undefined
const safeFixed = (v: number | null | undefined, d: number): string =>
  v == null || isNaN(v) ? '—' : v.toFixed(d)

interface RiskMetricRowsProps {
  analytics: AnalyticsData
  diversification: Diversification | undefined
  xirr: number | null | undefined
}

export default function RiskMetricRows({ analytics, diversification, xirr }: RiskMetricRowsProps) {
  return (
    <>
      {/* Rangée 1 : risque cœur */}
      <SpotlightGroup className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="volatility">
              <CardTitle className="text-sm font-medium">Volatilité</CardTitle>
            </MetricWithTooltip>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium">{safeFixed(analytics.portfolio_volatility, 1)}%</div>
            <p className="text-xs text-muted-foreground">
              {analytics.portfolio_volatility < 30 ? 'Faible' : analytics.portfolio_volatility < 60 ? 'Modérée' : 'Élevée'}
            </p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="sharpe">
              <CardTitle className="text-sm font-medium">Sharpe</CardTitle>
            </MetricWithTooltip>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(analytics.sharpe_ratio ?? 0) >= 1 ? 'text-gain' : (analytics.sharpe_ratio ?? 0) >= 0 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(analytics.sharpe_ratio, 2)}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.sharpe_ratio >= 2 ? 'Excellent' : analytics.sharpe_ratio >= 1 ? 'Bon' : analytics.sharpe_ratio >= 0 ? 'Moyen' : 'Faible'}
            </p>
            {analytics.interpretations?.sharpe && (
              <p className="text-xs text-muted-foreground/80 mt-1.5 italic leading-snug">
                {analytics.interpretations.sharpe}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card relative ring-1 ring-accent/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <MetricWithTooltip metricKey="sortino">
                <CardTitle className="text-sm font-medium">Sortino</CardTitle>
              </MetricWithTooltip>
              <span className="inline-flex items-center gap-0.5 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent dark:text-accent">
                <Zap className="h-2.5 w-2.5" /> Crypto
              </span>
            </div>
            <Shield className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(analytics.sortino_ratio ?? 0) >= 1 ? 'text-gain' : (analytics.sortino_ratio ?? 0) >= 0 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(analytics.sortino_ratio, 2)}
            </div>
            <p className="text-xs text-muted-foreground">
              Ne punit pas les hausses explosives
            </p>
            {analytics.interpretations?.sortino && (
              <p className="text-xs text-muted-foreground/80 mt-1.5 italic leading-snug">
                {analytics.interpretations.sortino}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="diversification">
              <CardTitle className="text-sm font-medium">Diversification</CardTitle>
            </MetricWithTooltip>
            <PieChartIcon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-serif font-medium ${(diversification?.score || 0) >= 60 ? 'text-gain' : (diversification?.score || 0) >= 40 ? 'text-warning' : 'text-loss'}`}>
              {safeFixed(diversification?.score, 0)}/100
            </div>
            <p className="text-xs text-muted-foreground">{diversification?.rating}</p>
          </CardContent>
        </Card>
      </SpotlightGroup>

      {/* Rangée 2 : risque extrême + XIRR */}
      <SpotlightGroup className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="var">
              <CardTitle className="text-sm font-medium">VaR 95%</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {analytics.var_95 != null ? formatCurrency(Math.abs(analytics.var_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">
              {analytics.var_95_description || 'Perte max/jour (95%)'}
            </p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="cvar">
              <CardTitle className="text-sm font-medium">CVaR (ES)</CardTitle>
            </MetricWithTooltip>
            <ArrowDownRight className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {analytics.cvar_95 != null ? formatCurrency(Math.abs(analytics.cvar_95)) : '—'}
            </div>
            <p className="text-xs text-muted-foreground">Expected Shortfall</p>
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="maxdd">
              <CardTitle className="text-sm font-medium">Max Drawdown</CardTitle>
            </MetricWithTooltip>
            <TrendingDown className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">
              {safeFixed(analytics.max_drawdown, 1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              Calmar: {safeFixed(analytics.calmar_ratio, 2)}
            </p>
            {analytics.interpretations?.calmar && (
              <p className="text-xs text-muted-foreground/80 mt-1 italic leading-snug">
                {analytics.interpretations.calmar}
              </p>
            )}
          </CardContent>
        </Card>

        <Card elevation="raised" className="spot-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <MetricWithTooltip metricKey="xirr">
              <CardTitle className="text-sm font-medium">XIRR</CardTitle>
            </MetricWithTooltip>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {xirr != null ? (
              <>
                <div className={`text-2xl font-serif font-medium ${xirr >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {xirr > 0 ? '+' : ''}{xirr.toFixed(2)}%
                </div>
                <p className="text-xs text-muted-foreground">Rendement annualisé réel</p>
              </>
            ) : (
              <>
                <div className="text-2xl font-serif font-medium text-muted-foreground">—</div>
                <p className="text-xs text-muted-foreground">Pas assez de données</p>
              </>
            )}
          </CardContent>
        </Card>
      </SpotlightGroup>
    </>
  )
}
