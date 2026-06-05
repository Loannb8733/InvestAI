import { useId, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { formatCurrency } from '@/lib/utils'
import { insightsApi, predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { ResponsiveBar } from '@nivo/bar'
import { ResponsiveLine, type LineSeries } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import {
  Receipt,
  Scissors,
  Coins,
  TrendingUp,
  Loader2,
  AlertTriangle,
  DollarSign,
  Calendar,
  Lightbulb,
  Play,
  Zap,
  ShieldAlert,
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Shield,
} from 'lucide-react'

interface TaxLossOpportunity {
  symbol: string
  asset_type: string
  avg_buy_price: number
  current_price: number
  current_value: number
  unrealized_loss: number
  unrealized_loss_pct: number
  potential_tax_saving: number
}

type Tab = 'alpha' | 'fees' | 'harvest' | 'income' | 'dca'

export default function InsightsPage() {
  const [tab, setTab] = useState<Tab>('alpha')

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'alpha', label: 'Top Alpha', icon: <Zap className="h-4 w-4" /> },
    { id: 'fees', label: 'Frais', icon: <Receipt className="h-4 w-4" /> },
    { id: 'harvest', label: 'Tax-Loss', icon: <Scissors className="h-4 w-4" /> },
    { id: 'income', label: 'Revenus passifs', icon: <Coins className="h-4 w-4" /> },
    { id: 'dca', label: 'Backtest DCA', icon: <TrendingUp className="h-4 w-4" /> },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-medium">Insights</h1>
        <p className="text-muted-foreground">Analyse avancée de votre portefeuille</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 flex-wrap">
        {tabs.map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            <span className="ml-1.5">{t.label}</span>
          </Button>
        ))}
      </div>

      {tab === 'alpha' && (
        <>
          <TopAlpha />
          <StrategyTable />
        </>
      )}
      {tab === 'fees' && <FeeAnalysis />}
      {tab === 'harvest' && <TaxLossHarvesting />}
      {tab === 'income' && <PassiveIncome />}
      {tab === 'dca' && <DcaBacktest />}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Top Alpha Tab
// ──────────────────────────────────────────────────────

interface AlphaReason {
  label: string
  detail: string
  score: number
}

interface AlphaAsset {
  symbol: string
  name: string
  asset_type: string
  current_price: number
  score: number
  predicted_7d_pct: number
  prediction_source?: string
  reasons: AlphaReason[]
  regime: string
  regime_confidence: number
  value: number
  weight_pct: number
}

function TopAlpha() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.predictions.topAlpha,
    queryFn: predictionsApi.getTopAlpha,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />
  if (!data || !data.found) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Zap className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">Aucun actif risqué détecté</h3>
          <p className="text-muted-foreground mt-1">
            L'analyse Alpha nécessite des positions en cryptomonnaies, actions ou ETF. Les stablecoins et le cash sont exclus.
          </p>
        </CardContent>
      </Card>
    )
  }

  const top: AlphaAsset = data.top_alpha
  const allScores: AlphaAsset[] = data.all_scores || []
  const concentrationRisk: boolean = data.concentration_risk

  const scoreColor = top.score >= 80 ? 'text-gain' : top.score >= 50 ? 'text-warning' : 'text-muted-foreground'
  const predColor = top.predicted_7d_pct >= 0 ? 'text-gain' : 'text-loss'

  return (
    <div className="space-y-4">
      {/* Main Alpha Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-warning" />
                Potentiel de Sursaut
              </CardTitle>
              <CardDescription>
                Actif avec la meilleure configuration technique à court terme
              </CardDescription>
            </div>
            <div className="text-right">
              <div className={`text-3xl font-serif font-medium ${scoreColor}`}>{top.score.toFixed(0)}</div>
              <div className="text-xs text-muted-foreground">/100</div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Concentration Risk Warning */}
          {concentrationRisk && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-warning dark:bg-warning/30 border border-warning dark:border-warning">
              <ShieldAlert className="h-4 w-4 text-warning shrink-0" />
              <p className="text-sm text-warning dark:text-warning">
                Cet actif représente déjà {top.weight_pct.toFixed(0)}% de votre portefeuille.
                Prudence avant de renforcer.
              </p>
            </div>
          )}

          {/* Asset Header */}
          <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
            <div>
              <div className="text-lg font-bold">{top.symbol}</div>
              <div className="text-sm text-muted-foreground">{top.name}</div>
              <Badge variant="outline" className="mt-1">{top.asset_type}</Badge>
            </div>
            <div className="text-right">
              <div className="text-sm text-muted-foreground">Prix actuel</div>
              <div className="text-lg font-semibold">{formatCurrency(top.current_price)}</div>
              <div className={`text-sm font-medium ${predColor}`}>
                {top.predicted_7d_pct >= 0 ? '+' : ''}{top.predicted_7d_pct.toFixed(2)}% prédit à 7j
                {top.prediction_source === 'ema20_slope' && (
                  <span className="text-[10px] text-muted-foreground ml-1">(EMA)</span>
                )}
              </div>
            </div>
          </div>

          {/* Reasons */}
          <div>
            <h4 className="text-sm font-semibold mb-2">Raisons techniques</h4>
            <div className="space-y-2">
              {top.reasons.map((reason, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg border">
                  <div>
                    <div className="text-sm font-medium">{reason.label}</div>
                    <div className="text-xs text-muted-foreground">{reason.detail}</div>
                  </div>
                  <Badge variant={reason.score >= 20 ? 'default' : 'secondary'}>
                    +{reason.score}
                  </Badge>
                </div>
              ))}
              {top.reasons.length === 0 && (
                <p className="text-sm text-muted-foreground">Aucun signal technique fort détecté.</p>
              )}
            </div>
          </div>

          {/* Regime Info */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Lightbulb className="h-4 w-4" />
            Régime: <Badge variant="outline">{top.regime}</Badge>
            (confiance {(top.regime_confidence * 100).toFixed(0)}%)
          </div>
        </CardContent>
      </Card>

      {/* Scoreboard — other assets */}
      {allScores.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Classement Alpha</CardTitle>
            <CardDescription>Tous vos actifs classés par score de surperformance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {allScores.map((asset, i) => (
                <div key={asset.symbol} className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-bold text-muted-foreground w-5">{i + 1}</span>
                    <div>
                      <span className="font-medium">{asset.symbol}</span>
                      <span className="text-xs text-muted-foreground ml-2">{asset.name}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`text-sm ${asset.predicted_7d_pct >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {asset.predicted_7d_pct >= 0 ? '+' : ''}{asset.predicted_7d_pct.toFixed(2)}%
                    </span>
                    <Badge variant={asset.score >= 60 ? 'default' : 'secondary'}>
                      {asset.score.toFixed(0)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Strategy Table — Decision Matrix Alpha × Cycle
// ──────────────────────────────────────────────────────

interface StrategyRow {
  symbol: string
  name: string
  alpha_score: number
  alpha_level: string
  regime: string
  regime_confidence: number
  action: string
  description: string
  value: number
  weight_pct: number
  impact_pct: number
  impact_eur: number
  predicted_7d_pct: number
  is_resilient?: boolean
}

interface StrategyMapData {
  rows: StrategyRow[]
  total_portfolio_value: number
  market_regime: string
  fear_greed: number | null
  summary: { buys: number; sells: number; holds: number }
}

const regimeLabels: Record<string, string> = {
  bullish: 'Mark-up', bearish: 'Markdown', top: 'Topping', bottom: 'Bottoming',
  markup: 'Mark-up', markdown: 'Markdown', topping: 'Topping', bottoming: 'Bottoming',
  accumulation: 'Accumulation', distribution: 'Distribution',
}
const regimeColors: Record<string, string> = {
  bullish: 'bg-gain/10 text-gain border-gain/30',
  bearish: 'bg-loss/10 text-loss border-loss/30',
  top: 'bg-warning/10 text-warning border-warning/30',
  bottom: 'bg-accent/10 text-accent border-accent/30',
  markup: 'bg-gain/10 text-gain border-gain/30',
  markdown: 'bg-loss/10 text-loss border-loss/30',
  topping: 'bg-warning/10 text-warning border-warning/30',
  bottoming: 'bg-accent/10 text-accent border-accent/30',
  accumulation: 'bg-warning/10 text-warning border-warning/30',
  distribution: 'bg-accent/10 text-accent border-accent/30',
}

const actionStyles: Record<string, string> = {
  'ACHAT FORT': 'bg-gain text-white',
  'DCA': 'bg-gain/10 text-gain border border-gain/30',
  'MAINTENIR': 'bg-gray-500/10 text-gray-700 border border-gray-500/30',
  'CONSERVER': 'bg-gray-500/10 text-gray-700 border border-gray-500/30',
  'OBSERVER': 'bg-accent/10 text-accent border border-accent/30',
  'ATTENDRE': 'bg-warning/10 text-warning border border-warning/30',
  'ÉVITER': 'bg-warning/10 text-warning border border-warning/30',
  'PRENDRE PROFITS': 'bg-warning/10 text-warning border border-warning/30',
  'ALLÉGER': 'bg-warning/10 text-warning border border-warning/30',
  'VENDRE': 'bg-loss text-white',
  'PLANIFIER': 'bg-accent/10 text-accent border border-accent/30',
}

interface PlannedOrder {
  id: string
  symbol: string
  action: string
  order_eur: number
  source: string
  status: string
  created_at: string | null
}

function StrategyTable() {
  const { data, isLoading } = useQuery<StrategyMapData>({
    queryKey: queryKeys.predictions.strategyMap,
    queryFn: predictionsApi.getStrategyMap,
    staleTime: 5 * 60 * 1000,
  })

  const { data: plannedOrders } = useQuery<PlannedOrder[]>({
    queryKey: queryKeys.predictions.plannedOrders,
    queryFn: predictionsApi.getPlannedOrders,
    staleTime: 30 * 1000,
  })

  const [signalModalOpen, setSignalModalOpen] = useState(false)
  const validateSignalMutation = useMutation({
    mutationFn: predictionsApi.validateSignal,
  })

  const handleActionClick = (row: StrategyRow) => {
    setSignalModalOpen(true)
    validateSignalMutation.mutate({ symbol: row.symbol, action: row.action })
  }

  if (isLoading) return <StrategyTableSkeleton />
  if (!data || data.rows.length === 0) return null

  // Set of symbols with pending planned orders
  const plannedSymbols = new Set(
    (plannedOrders || []).filter(o => o.status === 'pending').map(o => o.symbol)
  )

  const totalImpact = data.rows.reduce((sum, r) => sum + r.impact_eur, 0)
  const signal = validateSignalMutation.data

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Matrice de Stratégie
              </CardTitle>
              <CardDescription>
                Croisement Alpha × Cycle pour chaque actif — actions recommandées
              </CardDescription>
            </div>
            <div className="flex items-center gap-3 text-sm">
              {data.summary.buys > 0 && (
                <Badge className="bg-gain/10 text-gain border border-gain/30">
                  {data.summary.buys} Achat{data.summary.buys > 1 ? 's' : ''}
                </Badge>
              )}
              {data.summary.sells > 0 && (
                <Badge className="bg-loss/10 text-loss border border-loss/30">
                  {data.summary.sells} Vente{data.summary.sells > 1 ? 's' : ''}
                </Badge>
              )}
              {data.summary.holds > 0 && (
                <Badge variant="secondary">
                  {data.summary.holds} Maintien{data.summary.holds > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* Regime context banner */}
          {['bearish', 'bottom', 'bottoming', 'accumulation', 'markdown'].includes(data.market_regime) && (
            <div className="mb-4 rounded-lg border border-accent/30 bg-accent/5 p-3 flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 text-accent mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">
                <span className="font-semibold text-accent dark:text-accent">Mode Accumulation</span> — Les signaux DCA/ACHAT sont renforcés.
                Les prix sont décotés, accumulez sur les actifs à fort alpha. Les signaux de vente sont atténués.
              </p>
            </div>
          )}
          {['bullish', 'markup'].includes(data.market_regime) && (
            <div className="mb-4 rounded-lg border border-warning/30 bg-warning/5 p-3 flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 text-warning mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">
                <span className="font-semibold text-warning dark:text-warning">Mode Expansion</span> — Laissez courir vos positions mais préparez vos niveaux de sortie.
                Réduisez les montants DCA et définissez vos objectifs de prise de profits.
              </p>
            </div>
          )}
          {['top', 'topping', 'distribution'].includes(data.market_regime) && (
            <div className="mb-4 rounded-lg border border-loss/30 bg-loss/5 p-3 flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 text-loss mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">
                <span className="font-semibold text-loss dark:text-loss">Mode Prise de Profits</span> — Les signaux de vente sont prioritaires.
                Sécurisez vos gains partiellement, gardez du cash pour accumuler au prochain creux.
              </p>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Alpha</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Phase</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Action</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">Impact Portefeuille</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => {
                  const impactSign = row.impact_eur > 0 ? '+' : row.impact_eur < 0 ? '-' : ''
                  const isActionable = ['ACHAT FORT', 'DCA', 'VENDRE', 'ALLÉGER', 'PRENDRE PROFITS'].includes(row.action)

                  return (
                    <tr key={row.symbol} className={`border-b last:border-0 hover:bg-muted/50 ${plannedSymbols.has(row.symbol) ? 'bg-primary/5' : ''}`}>
                      <td className="py-3 px-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{row.symbol}</span>
                            {row.name !== row.symbol && (
                              <span className="text-xs text-muted-foreground">{row.name}</span>
                            )}
                            {row.is_resilient && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-warning/50 text-warning gap-0.5">
                                <Shield className="h-3 w-3" />
                                Bouclier
                              </Badge>
                            )}
                            {plannedSymbols.has(row.symbol) && (
                              <Badge className="bg-primary text-primary-foreground text-[10px] px-1.5 py-0">
                                À EXÉCUTER
                              </Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {formatCurrency(row.value)} · {row.weight_pct}%
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex flex-col items-center gap-0.5">
                          <span className={`text-sm font-bold ${
                            row.alpha_score >= 60 ? 'text-gain' :
                            row.alpha_score >= 30 ? 'text-warning' : 'text-muted-foreground'
                          }`}>
                            {row.alpha_score.toFixed(0)}
                          </span>
                          <span className="text-[10px] text-muted-foreground capitalize">{row.alpha_level}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant="outline" className={regimeColors[row.regime] || 'text-gray-500'}>
                          {regimeLabels[row.regime] || row.regime}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-center">
                        {isActionable ? (
                          <Badge
                            className={`text-xs cursor-pointer hover:opacity-80 transition-opacity ${actionStyles[row.action] || 'bg-gray-100 text-gray-700'}`}
                            onClick={() => handleActionClick(row)}
                          >
                            {row.action}
                          </Badge>
                        ) : (
                          <Badge className={`text-xs ${actionStyles[row.action] || 'bg-gray-100 text-gray-700'}`}>
                            {row.action}
                          </Badge>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {row.impact_eur > 0 ? (
                            <ArrowUpRight className="h-3 w-3 text-gain" />
                          ) : row.impact_eur < 0 ? (
                            <ArrowDownRight className="h-3 w-3 text-loss" />
                          ) : (
                            <Minus className="h-3 w-3 text-muted-foreground" />
                          )}
                          <span className={`text-sm font-medium tabular-nums ${
                            row.impact_eur > 0 ? 'text-gain' :
                            row.impact_eur < 0 ? 'text-loss' : 'text-muted-foreground'
                          }`}>
                            {impactSign}{formatCurrency(Math.abs(row.impact_eur))}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            ({row.impact_pct > 0 ? '+' : ''}{row.impact_pct}%)
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr className="border-t">
                  <td colSpan={4} className="py-3 px-3 text-sm font-medium text-right">
                    Impact total estimé
                  </td>
                  <td className="py-3 px-3 text-right">
                    <span className={`text-sm font-bold tabular-nums ${
                      totalImpact > 0 ? 'text-gain' :
                      totalImpact < 0 ? 'text-loss' : 'text-muted-foreground'
                    }`}>
                      {totalImpact > 0 ? '+' : ''}{formatCurrency(totalImpact)}
                    </span>
                    <span className="text-xs text-muted-foreground ml-1">
                      sur {formatCurrency(data.total_portfolio_value)}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-start gap-2 p-2 rounded bg-muted/30">
            <Lightbulb className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              L'action est déterminée par le croisement du score Alpha (potentiel technique) et de la phase du cycle de marché.
              Cliquez sur un badge actionnable pour valider le signal avec Monte Carlo.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Signal Validation Modal */}
      <Dialog open={signalModalOpen} onOpenChange={setSignalModalOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Validation du Signal
            </DialogTitle>
            <DialogDescription>
              Simulation Monte Carlo de l'impact sur la probabilité de ruine
            </DialogDescription>
          </DialogHeader>

          {validateSignalMutation.isPending ? (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </div>
              <Skeleton className="h-24 w-full" />
              <div className="grid grid-cols-2 gap-3">
                <Skeleton className="h-16" />
                <Skeleton className="h-16" />
              </div>
            </div>
          ) : validateSignalMutation.isError ? (
            <div className="py-6 text-center">
              <AlertTriangle className="h-8 w-8 mx-auto text-loss mb-2" />
              <p className="text-sm text-muted-foreground">Erreur lors de la validation du signal</p>
            </div>
          ) : signal ? (
            <div className="space-y-4 py-2">
              {/* Asset & Action */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div>
                  <div className="font-bold text-lg">{signal.symbol}</div>
                  <div className="text-sm text-muted-foreground">
                    Score: {signal.score}/100 · {signal.regime}
                  </div>
                </div>
                <div className="text-right">
                  <Badge className={actionStyles[signal.action] || 'bg-gray-100 text-gray-700'}>
                    {signal.action}
                  </Badge>
                  <div className="text-sm font-mono mt-1">{formatCurrency(signal.order_eur)}</div>
                </div>
              </div>

              {/* Monte Carlo comparison */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border text-center">
                  <p className="text-xs text-muted-foreground mb-1">Prob. de ruine AVANT</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{signal.prob_ruin_before}%</p>
                  <p className="text-xs text-muted-foreground">
                    P(+): {signal.mc_before?.prob_positive?.toFixed(1)}%
                  </p>
                </div>
                <div className={`p-3 rounded-lg border text-center ${
                  signal.prob_ruin_after <= signal.prob_ruin_before
                    ? 'border-gain/30 bg-gain/5'
                    : 'border-loss/30 bg-loss/5'
                }`}>
                  <p className="text-xs text-muted-foreground mb-1">Prob. de ruine APRÈS</p>
                  <p className="text-2xl font-serif font-medium tabular-nums">{signal.prob_ruin_after}%</p>
                  <p className="text-xs text-muted-foreground">
                    P(+): {signal.mc_after?.prob_positive?.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* Risk impact */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                <span className="text-sm font-medium">Impact risque</span>
                <Badge variant="outline" className={
                  signal.risk_impact === 'Diminuée' ? 'border-gain text-gain' :
                  signal.risk_impact === 'Augmentée' ? 'border-loss text-loss' :
                  'border-gray-500 text-gray-600'
                }>
                  {signal.risk_impact}
                </Badge>
              </div>

              {/* Concentration */}
              <div className="flex items-center justify-between text-sm">
                <span>Concentration post-achat</span>
                <span className={`font-mono font-medium ${
                  signal.concentration_status === 'ALERTE' ? 'text-loss' :
                  signal.concentration_status === 'VIGILANCE' ? 'text-warning' :
                  'text-gain'
                }`}>
                  {signal.post_purchase_weight_pct}% ({signal.concentration_status})
                </span>
              </div>

              {/* Verdict */}
              <div className={`p-3 rounded-lg text-center ${
                signal.validated
                  ? 'bg-gain/10 border border-gain/30'
                  : 'bg-loss/10 border border-loss/30'
              }`}>
                <p className={`font-bold ${signal.validated ? 'text-gain' : 'text-loss'}`}>
                  {signal.validated ? 'Signal validé' : 'Signal rejeté'}
                </p>
                {!signal.validated && signal.reason && (
                  <p className="text-xs text-muted-foreground mt-1">{signal.reason}</p>
                )}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  )
}

// ──────────────────────────────────────────────────────
// Fee Analysis Tab
// ──────────────────────────────────────────────────────
function FeeAnalysis() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.fees,
    queryFn: insightsApi.getFees,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.total_fees === 0) {
    return <EmptyState message="Aucun frais enregistré" />
  }

  const monthlyData = Object.entries((data.by_month ?? {}) as Record<string, number>).map(([month, value]) => ({
    month,
    fees: value,
  }))

  const exchangeData = Object.entries((data.by_exchange ?? {}) as Record<string, number>).map(([name, value]) => ({
    name,
    fees: value,
  }))

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total des frais</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">{formatCurrency(data.total_fees)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_transactions_with_fees} transactions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moyenne mensuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium">{formatCurrency(data.avg_monthly_fee)}</div>
            <p className="text-xs text-muted-foreground">par mois</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top exchange</CardTitle>
          </CardHeader>
          <CardContent>
            {exchangeData.length > 0 ? (
              <>
                <div className="text-2xl font-serif font-medium">{exchangeData[0].name}</div>
                <p className="text-xs text-muted-foreground">{formatCurrency(exchangeData[0].fees)}</p>
              </>
            ) : (
              <div className="text-muted-foreground">—</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Frais par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveBar
                data={monthlyData}
                keys={['fees']}
                indexBy="month"
                theme={theme}
                margin={{ top: 12, right: 16, bottom: 32, left: 56 }}
                padding={0.3}
                colors={() => color('--chart-4')}
                borderRadius={4}
                enableLabel={false}
                enableGridY
                axisBottom={{ tickSize: 0, tickPadding: 8 }}
                axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}€` }}
                valueScale={{ type: 'linear' }}
                tooltip={({ indexValue, value }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="mb-0.5 text-xs text-muted-foreground">{indexValue}</p>
                    <p className="font-mono text-sm tabular-nums">{formatCurrency(value)}</p>
                  </div>
                )}
                animate
                motionConfig="gentle"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Frais par exchange</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {exchangeData.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{item.name}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-loss rounded-full"
                        style={{ width: `${data.total_fees > 0 ? Math.min(100, (item.fees / data.total_fees) * 100) : 0}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono w-20 text-right">{formatCurrency(item.fees)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Tax-Loss Harvesting Tab
// ──────────────────────────────────────────────────────
function TaxLossHarvesting() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.taxLossHarvesting,
    queryFn: insightsApi.getTaxLossHarvesting,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_candidates === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <TrendingUp className="h-12 w-12 mx-auto text-gain mb-3" />
          <h3 className="text-lg font-semibold">Aucune opportunité</h3>
          <p className="text-muted-foreground text-sm mt-1">
            Toutes vos positions sont en plus-value. Pas de tax-loss harvesting possible.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Fiscal disclaimer */}
      <div className="flex items-start gap-2 rounded-md bg-warning/10 border border-warning/20 px-3 py-2">
        <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
        <p className="text-[11px] text-warning dark:text-warning leading-tight">
          Le Tax-Loss Harvesting est une stratégie fiscale soumise à des règles complexes (wash-sale, règles anti-abus).
          Ces informations sont fournies à titre indicatif uniquement et ne constituent pas un conseil fiscal.
          Consultez un conseiller fiscal agréé avant toute décision.
        </p>
      </div>
      {/* Summary */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moins-values totales</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-loss">{formatCurrency(data.total_harvestable)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_candidates} positions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Economie d'impôt estimée</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-gain">{formatCurrency(data.estimated_tax_saving)}</div>
            <p className="text-xs text-muted-foreground">Flat tax 30%</p>
          </CardContent>
        </Card>
        <Card className="border-warning/20 bg-warning/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              <Lightbulb className="h-4 w-4 text-warning" />
              Conseil
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">{data.note}</p>
          </CardContent>
        </Card>
      </div>

      {/* Opportunities table */}
      <Card>
        <CardHeader>
          <CardTitle>Opportunités de harvesting</CardTitle>
          <CardDescription>Positions en moins-value pouvant réduire votre impôt</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="text-left p-2">Actif</th>
                  <th scope="col" className="text-right p-2">PRU</th>
                  <th scope="col" className="text-right p-2">Prix actuel</th>
                  <th scope="col" className="text-right p-2">Valeur</th>
                  <th scope="col" className="text-right p-2">Moins-value</th>
                  <th scope="col" className="text-right p-2">%</th>
                  <th scope="col" className="text-right p-2">Eco. impôt</th>
                </tr>
              </thead>
              <tbody>
                {(data.opportunities as TaxLossOpportunity[]).map((op) => (
                  <tr key={op.symbol} className="border-b last:border-b-0">
                    <td className="p-2">
                      <span className="font-medium">{op.symbol}</span>
                      <Badge variant="outline" className="ml-1 text-xs">{op.asset_type}</Badge>
                    </td>
                    <td className="text-right p-2">{formatCurrency(op.avg_buy_price)}</td>
                    <td className="text-right p-2">{formatCurrency(op.current_price)}</td>
                    <td className="text-right p-2">{formatCurrency(op.current_value)}</td>
                    <td className="text-right p-2 text-loss font-medium">{formatCurrency(op.unrealized_loss)}</td>
                    <td className="text-right p-2 text-loss">{op.unrealized_loss_pct.toFixed(1)}%</td>
                    <td className="text-right p-2 text-gain">{formatCurrency(op.potential_tax_saving)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Passive Income Tab
// ──────────────────────────────────────────────────────
function PassiveIncome() {
  const { theme, color } = useNivoTheme()
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.insights.passiveIncome,
    queryFn: () => insightsApi.getPassiveIncome(),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_events === 0) {
    return <EmptyState message="Aucun revenu passif enregistré (staking, airdrops)" />
  }

  const monthlyData = Object.entries((data.by_month ?? {}) as Record<string, number>).map(([month, value]) => ({
    month,
    income: value,
  }))

  const typeLabels: Record<string, string> = {
    staking_reward: 'Reward',
    airdrop: 'Airdrops',
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total revenus passifs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-gain">{formatCurrency(data.total_income)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_events} versements</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moyenne mensuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium">{formatCurrency(data.avg_monthly)}</div>
            <p className="text-xs text-muted-foreground">par mois</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Projection annuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-serif font-medium text-accent">{formatCurrency(data.projected_annual)}</div>
            <p className="text-xs text-muted-foreground">basé sur les 3 derniers mois</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenus par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveBar
                data={monthlyData}
                keys={['income']}
                indexBy="month"
                theme={theme}
                margin={{ top: 12, right: 16, bottom: 32, left: 56 }}
                padding={0.3}
                colors={() => color('--chart-3')}
                borderRadius={4}
                enableLabel={false}
                enableGridY
                axisBottom={{ tickSize: 0, tickPadding: 8 }}
                axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}€` }}
                valueScale={{ type: 'linear' }}
                tooltip={({ indexValue, value }) => (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                    <p className="mb-0.5 text-xs text-muted-foreground">{indexValue}</p>
                    <p className="font-mono text-sm tabular-nums">{formatCurrency(value)}</p>
                  </div>
                )}
                animate
                motionConfig="gentle"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Par type</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries((data.by_type ?? {}) as Record<string, number>).map(([type, value]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{typeLabels[type] || type}</span>
                  <span className="text-sm font-mono text-gain">{formatCurrency(value)}</span>
                </div>
              ))}
              {Object.keys((data.by_asset ?? {}) as Record<string, number>).length > 0 && (
                <>
                  <div className="border-t pt-3 mt-3">
                    <p className="text-xs text-muted-foreground mb-2">Par actif :</p>
                    {Object.entries((data.by_asset ?? {}) as Record<string, number>).map(([sym, val]) => (
                      <div key={sym} className="flex items-center justify-between py-1">
                        <span className="text-sm">{sym}</span>
                        <span className="text-xs font-mono">{formatCurrency(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// DCA Backtest Tab
// ──────────────────────────────────────────────────────
function DcaBacktest() {
  const { theme, color } = useNivoTheme()
  const uid = useId().replace(/:/g, '')
  const [symbol, setSymbol] = useState('BTC')
  const [assetType, setAssetType] = useState('crypto')
  const [amount, setAmount] = useState(100)
  const [startYear, setStartYear] = useState(2021)
  const [started, setStarted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: queryKeys.insights.dcaBacktest(symbol, assetType, amount, startYear),
    queryFn: () => insightsApi.backtestDca(symbol, assetType, amount, startYear),
    enabled: started,
    staleTime: 10 * 60 * 1000,
  })

  const handleRun = () => {
    if (started) {
      refetch()
    } else {
      setStarted(true)
    }
  }

  const chartData: { month: string; invested: number; value: number }[] =
    data?.monthly_history?.map((m: { month: string; invested: number; value: number }) => ({
      month: m.month,
      invested: m.invested,
      value: m.value,
    })) || []

  const dcaSeries: LineSeries[] = [
    { id: 'invested', data: chartData.map((m) => ({ x: m.month, y: m.invested })) },
    { id: 'value', data: chartData.map((m) => ({ x: m.month, y: m.value })) },
  ]
  const dcaLabels: Record<string, string> = { invested: 'Investi', value: 'Valeur' }
  const dcaColors: Record<string, string> = {
    invested: color('--muted-foreground'),
    value: color('--chart-3'),
  }
  const dcaTickValues = (() => {
    if (chartData.length === 0) return [] as string[]
    const target = Math.min(6, chartData.length)
    const step = Math.max(1, Math.floor(chartData.length / target))
    return chartData.filter((_, i) => i % step === 0).map((m) => m.month)
  })()

  return (
    <div className="space-y-4">
      {/* Config form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Configuration du backtest DCA
          </CardTitle>
          <CardDescription>
            Simulez un investissement mensuel automatique sur un actif
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-5">
            <div>
              <Label>Symbole</Label>
              <Input value={symbol} onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setStarted(false) }} placeholder="BTC" />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={assetType} onValueChange={(v) => { setAssetType(v); setStarted(false) }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="crypto">Crypto</SelectItem>
                  <SelectItem value="stock">Action</SelectItem>
                  <SelectItem value="etf">ETF</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Montant/mois (EUR)</Label>
              <Input type="number" value={amount} onChange={(e) => { setAmount(+e.target.value); setStarted(false) }} min={1} />
            </div>
            <div>
              <Label>Depuis</Label>
              <Input type="number" value={startYear} onChange={(e) => { setStartYear(+e.target.value); setStarted(false) }} min={2010} max={new Date().getFullYear()} />
            </div>
            <div className="flex items-end">
              <Button onClick={handleRun} disabled={isLoading} className="w-full">
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 mr-1" />}
                Lancer
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {data && !data.error && (
        <>
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Total investi</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">{formatCurrency(data.total_invested)}</div>
                <p className="text-xs text-muted-foreground">{data.nb_months} mois</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Valeur actuelle</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {formatCurrency(data.current_value)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Plus-value</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {data.gain_loss >= 0 ? '+' : ''}{formatCurrency(data.gain_loss)}
                </div>
                <p className="text-xs text-muted-foreground">{data.gain_loss_pct >= 0 ? '+' : ''}{Number(data.gain_loss_pct).toFixed(2)}%</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Prix moyen</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">{formatCurrency(data.avg_buy_price)}</div>
                <p className="text-xs text-muted-foreground">vs {formatCurrency(data.current_price)} actuel</p>
              </CardContent>
            </Card>
          </div>

          {chartData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Evolution : investissement vs valeur</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveLine
                    data={dcaSeries}
                    theme={theme}
                    margin={{ top: 28, right: 16, bottom: 28, left: 56 }}
                    xScale={{ type: 'point' }}
                    yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
                    curve="monotoneX"
                    colors={(s) => dcaColors[s.id as string]}
                    lineWidth={2}
                    enablePoints={false}
                    enableGridX={false}
                    enableArea
                    areaOpacity={1}
                    defs={[
                      {
                        id: `${uid}-value`,
                        type: 'linearGradient',
                        colors: [
                          { offset: 0, color: dcaColors.value, opacity: 0.3 },
                          { offset: 100, color: dcaColors.value, opacity: 0 },
                        ],
                      },
                    ]}
                    fill={[
                      { match: { id: 'value' }, id: `${uid}-value` },
                      { match: { id: 'invested' }, id: 'none' },
                    ]}
                    axisBottom={{ tickSize: 0, tickPadding: 8, tickValues: dcaTickValues }}
                    axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${(Number(v) / 1000).toFixed(0)}k€` }}
                    enableSlices="x"
                    sliceTooltip={({ slice }) => (
                      <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                        <p className="mb-1.5 text-xs text-muted-foreground">{slice.points[0]?.data.x as string}</p>
                        {slice.points.map((p) => (
                          <div key={p.id} className="flex items-center justify-between gap-4">
                            <span className="flex items-center gap-2">
                              <span
                                className="h-2 w-2 rounded-[2px]"
                                style={{ backgroundColor: dcaColors[p.seriesId as string] }}
                              />
                              <span className="text-xs text-muted-foreground">
                                {dcaLabels[p.seriesId as string] ?? p.seriesId}
                              </span>
                            </span>
                            <span className="font-mono text-sm tabular-nums">
                              {formatCurrency(p.data.y as number)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    legends={[
                      {
                        anchor: 'top-right',
                        direction: 'row',
                        translateY: -22,
                        itemWidth: 90,
                        itemHeight: 18,
                        symbolSize: 10,
                        symbolShape: 'circle',
                        itemTextColor: color('--muted-foreground'),
                        data: [
                          { id: 'value', label: dcaLabels.value, color: dcaColors.value },
                          { id: 'invested', label: dcaLabels.invested, color: dcaColors.invested },
                        ],
                      },
                    ]}
                    animate
                    motionConfig="gentle"
                  />
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {data?.error && (
        <Card className="border-loss/20">
          <CardContent className="py-6 text-center">
            <AlertTriangle className="h-8 w-8 mx-auto text-loss mb-2" />
            <p className="text-sm text-loss">{data.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Shared components
// ──────────────────────────────────────────────────────
function Loader() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-72 mt-1" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
        <div className="flex gap-3 mt-4">
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-10 w-24" />
        </div>
      </CardContent>
    </Card>
  )
}

function StrategyTableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-44" />
        <Skeleton className="h-4 w-80 mt-1" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-6 w-12" />
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-4 w-24 ml-auto" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <DollarSign className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
        <p className="text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  )
}
