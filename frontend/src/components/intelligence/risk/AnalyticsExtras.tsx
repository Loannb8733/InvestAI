import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import {
  Activity,
  HelpCircle,
  Info,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'
import type { BetaData, Diversification, PerformanceSummary } from './types'

/**
 * Compléments Analytics conservés dans le pilier : Beta vs Benchmark,
 * recommandations de diversification, meilleurs/pires performers.
 * Copiés d'AnalyticsPage (mêmes données, mêmes seuils).
 */

// ── Beta vs Benchmark ─────────────────────────────────────────────────

interface BetaCardProps {
  betaData: BetaData
  betaDays: number
  periodDays: number
}

export function BetaCard({ betaData, betaDays, periodDays }: BetaCardProps) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-accent" />
          Beta vs Benchmark
        </CardTitle>
        <CardDescription>
          Sensibilité de vos actifs par rapport au marché
          {periodDays > 0 && periodDays < 30 && (
            <span className="block text-xs text-warning mt-1">
              Min. 30 jours requis pour le beta (calculé sur {betaDays}j)
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Betas de portefeuille */}
          <div className="grid grid-cols-2 gap-3 pb-3 border-b">
            {betaData.portfolio_beta_crypto != null && (
              <div className="text-center">
                <div className={`text-lg font-bold ${betaData.portfolio_beta_crypto > 1 ? 'text-loss' : betaData.portfolio_beta_crypto > 0.5 ? 'text-warning' : 'text-gain'}`}>
                  {betaData.portfolio_beta_crypto.toFixed(2)}
                </div>
                <div className="text-xs text-muted-foreground">Beta vs BTC</div>
              </div>
            )}
            {betaData.portfolio_beta_stock != null && (
              <div className="text-center">
                <div className={`text-lg font-bold ${betaData.portfolio_beta_stock > 1 ? 'text-loss' : betaData.portfolio_beta_stock > 0.5 ? 'text-warning' : 'text-gain'}`}>
                  {betaData.portfolio_beta_stock.toFixed(2)}
                </div>
                <div className="text-xs text-muted-foreground">Beta vs SPY</div>
              </div>
            )}
          </div>

          {/* Betas par actif */}
          <div className="space-y-2">
            {betaData.assets.slice(0, 8).map((asset) => (
              <div key={asset.symbol} className="flex items-center gap-2">
                <span className="text-sm font-medium w-14">{asset.symbol}</span>
                <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden relative">
                  {asset.beta != null && (
                    <>
                      {/* Ligne de référence à beta = 1 */}
                      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-foreground/20" />
                      <div
                        className={`h-full rounded-full absolute ${asset.beta > 1 ? 'bg-loss' : asset.beta > 0.5 ? 'bg-warning' : 'bg-gain'}`}
                        style={{
                          width: `${Math.min(100, Math.abs(asset.beta) * 50)}%`,
                          left: asset.beta >= 0 ? '0%' : undefined,
                          right: asset.beta < 0 ? '50%' : undefined,
                        }}
                      />
                    </>
                  )}
                </div>
                <span className="text-xs font-mono w-10 text-right">
                  {asset.beta != null ? asset.beta.toFixed(2) : '—'}
                </span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger aria-label={`Aide sur le beta de ${asset.symbol}`}>
                      <HelpCircle className="h-3 w-3 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      <p className="text-xs">{asset.interpretation}</p>
                      <p className="text-xs text-muted-foreground mt-1">Benchmark: {asset.benchmark}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Recommandations de diversification ────────────────────────────────

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case 'high': return 'text-loss'
    case 'medium': return 'text-warning'
    default: return 'text-accent'
  }
}

const getSeverityBg = (severity: string) => {
  switch (severity) {
    case 'high': return 'bg-loss/10 border-loss/20'
    case 'medium': return 'bg-warning/10 border-warning/20'
    default: return 'bg-accent/10 border-accent/20'
  }
}

interface DiversificationRecommendationsProps {
  diversification: Diversification
}

export function DiversificationRecommendations({ diversification }: DiversificationRecommendationsProps) {
  if (diversification.recommendations.length === 0) return null
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-warning" />
          Recommandations de diversification
        </CardTitle>
        <CardDescription>Actions suggérées pour équilibrer l'allocation</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2">
          {diversification.recommendations.map((rec, index) => (
            <div key={index} className={`p-4 rounded-lg border ${getSeverityBg(rec.severity)}`}>
              <div className="flex items-start gap-3">
                <Info className={`h-5 w-5 mt-0.5 shrink-0 ${getSeverityColor(rec.severity)}`} />
                <div>
                  <p className="font-medium text-sm">{rec.message}</p>
                  <p className="text-xs text-muted-foreground mt-1">{rec.action}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Meilleurs / pires performers ──────────────────────────────────────

interface TopWorstPerformersProps {
  performance: PerformanceSummary
}

export function TopWorstPerformers({ performance }: TopWorstPerformersProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-gain">
            <TrendingUp className="h-5 w-5" />
            Meilleurs performers
          </CardTitle>
        </CardHeader>
        <CardContent>
          {performance.top_gainers && performance.top_gainers.length > 0 ? (
            <div className="space-y-3">
              {performance.top_gainers.map((item) => (
                <div key={item.symbol} className="flex items-center justify-between">
                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                  <span className="text-gain font-medium">+{item.gain_loss_percent.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">Aucun gain sur cette période</p>
          )}
        </CardContent>
      </Card>

      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-loss">
            <TrendingDown className="h-5 w-5" />
            Moins bons performers
          </CardTitle>
        </CardHeader>
        <CardContent>
          {performance.top_losers && performance.top_losers.length > 0 ? (
            <div className="space-y-3">
              {performance.top_losers.map((item) => (
                <div key={item.symbol} className="flex items-center justify-between">
                  <AssetIconCompact symbol={item.symbol} name={item.name} assetType={item.asset_type} size={36} />
                  <span className="text-loss font-medium">{item.gain_loss_percent.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">Aucune perte sur cette période</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
