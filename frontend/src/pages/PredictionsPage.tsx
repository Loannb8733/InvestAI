import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCurrency } from '@/lib/utils'
import { usePredictionData } from '@/hooks/usePredictionData'
import { FearGreedGauge } from '@/components/predictions/PredictionMetricCard'
import PredictionListView from '@/components/predictions/PredictionListView'
import PredictionCyclesTab from '@/components/predictions/PredictionCyclesTab'
import PredictionSignalsTab from '@/components/predictions/PredictionSignalsTab'
import PredictionSimulationTab from '@/components/predictions/PredictionSimulationTab'
import {
  AlertTriangle,
  Brain,
  Loader2,
  ArrowUp,
  ArrowDown,
  ShieldAlert,
  Zap,
  FlaskConical,
  BarChart3,
  Bell,
  Repeat,
} from 'lucide-react'

export default function PredictionsPage() {
  const {
    daysAhead, setDaysAhead,
    selectedAsset, setSelectedAsset,
    showReality, setShowReality,
    whatIfSymbol, setWhatIfSymbol,
    whatIfChange, setWhatIfChange,
    whatIfResult, whatIfLoading, runWhatIf,
    predictions, summary, dt,
    anomalies, anomaliesError,
    sentiment, sentimentError,
    marketCycle,
    backtestData,
    loadingPredictions, loadingSentiment, loadingCycle, loadingBacktest,
    selectedPrediction, chartData, showSupportResistance,
    unifiedAlerts, totalAlerts, highAlerts,
    formatPrice,
  } = usePredictionData()

  if (loadingPredictions || loadingSentiment) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Disclaimer banner */}
      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-yellow-600 dark:text-yellow-400">Analyse exploratoire</p>
          <p className="text-xs text-muted-foreground mt-1">
            Ces projections sont basées sur des modèles statistiques appliqués aux prix historiques.
            Elles ne constituent pas des conseils d'investissement. Les marchés crypto sont hautement
            imprévisibles — aucun modèle ne peut prédire l'avenir de manière fiable.
          </p>
        </div>
      </div>

      {/* Bear market mode banner */}
      {marketCycle?.market_regime?.dominant_regime === 'bearish' && (marketCycle?.market_regime?.confidence ?? 0) > 0.5 && (
        <div className="rounded-lg border-2 border-red-500/40 bg-red-500/5 p-4 flex items-start gap-3">
          <ShieldAlert className="h-6 w-6 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-bold text-red-600 dark:text-red-400 flex items-center gap-2">
              Mode marché baissier actif
              <Badge variant="destructive" className="text-xs">
                Confiance {((marketCycle?.market_regime?.confidence ?? 0) * 100).toFixed(0)}%
              </Badge>
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Les projections tiennent compte du régime baissier détecté.
              Les prédictions haussières ont été atténuées et les intervalles de confiance élargis.
              Privilégiez la prudence et le DCA progressif.
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Analyse & Projections</h1>
          <p className="text-muted-foreground">Projections statistiques et sentiment de marché</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={daysAhead <= 7 ? 'default' : daysAhead <= 14 ? 'secondary' : 'outline'} className="text-xs">
            Confiance : {daysAhead <= 7 ? 'Haute' : daysAhead <= 14 ? 'Modérée' : 'Indicative'}
          </Badge>
          <Select value={daysAhead.toString()} onValueChange={(v) => setDaysAhead(parseInt(v))}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7j — Court terme</SelectItem>
              <SelectItem value="14">14j — Moyen terme</SelectItem>
              <SelectItem value="30">30j — Tendance</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Sentiment + Portfolio Summary */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
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

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-5 w-5 text-primary" />
              <span className="font-semibold">Prévision portefeuille</span>
              <span className="text-xs text-muted-foreground ml-auto">{summary?.days_ahead ?? daysAhead}j</span>
            </div>
            {summary ? (
              <div className="space-y-4">
                <div className="text-center">
                  <div className={`text-4xl font-bold flex items-center justify-center gap-2 ${summary.expected_change_percent >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {summary.expected_change_percent >= 0 ? <ArrowUp className="h-7 w-7" /> : <ArrowDown className="h-7 w-7" />}
                    {Math.abs(summary.expected_change_percent).toFixed(2)}%
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {formatCurrency(summary.total_current_value)} → {formatCurrency(summary.total_predicted_value)}
                  </p>
                </div>
                <div className="space-y-2">
                  {(() => {
                    const total = summary.bullish_assets + summary.neutral_assets + summary.bearish_assets
                    return total > 0 ? (
                      <div className="flex h-3 rounded-full overflow-hidden bg-muted">
                        {summary.bullish_assets > 0 && <div className="bg-green-500 transition-all" style={{ width: `${(summary.bullish_assets / total) * 100}%` }} />}
                        {summary.neutral_assets > 0 && <div className="bg-yellow-500 transition-all" style={{ width: `${(summary.neutral_assets / total) * 100}%` }} />}
                        {summary.bearish_assets > 0 && <div className="bg-red-500 transition-all" style={{ width: `${(summary.bearish_assets / total) * 100}%` }} />}
                      </div>
                    ) : <div className="flex h-3 rounded-full overflow-hidden bg-muted" />
                  })()}
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" />{summary.bullish_assets} haussier</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" />{summary.neutral_assets} neutre</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" />{summary.bearish_assets} baissier</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">Aucune donnée</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="predictions" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="predictions" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />Projections
          </TabsTrigger>
          <TabsTrigger value="cycles" className="flex items-center gap-2">
            <Repeat className="h-4 w-4" />Cycles
          </TabsTrigger>
          <TabsTrigger value="signals" className="flex items-center gap-2">
            <Zap className="h-4 w-4" />Signaux
            {highAlerts > 0 && <span className="ml-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">{highAlerts}</span>}
          </TabsTrigger>
          <TabsTrigger value="simulation" className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />Simulation
          </TabsTrigger>
        </TabsList>

        <TabsContent value="predictions">
          {predictions && predictions.length > 0 ? (
            <PredictionListView
              predictions={predictions}
              selectedAsset={selectedAsset}
              setSelectedAsset={setSelectedAsset}
              selectedPrediction={selectedPrediction}
              chartData={chartData}
              showSupportResistance={showSupportResistance}
              showReality={showReality}
              setShowReality={setShowReality}
              loadingBacktest={loadingBacktest}
              backtestData={backtestData}
              daysAhead={daysAhead}
              dt={dt}
              formatPrice={formatPrice}
            />
          ) : (
            <Card><CardContent className="py-8 text-center"><p className="text-muted-foreground">Aucune prédiction disponible</p></CardContent></Card>
          )}
        </TabsContent>

        <TabsContent value="cycles">
          <PredictionCyclesTab marketCycle={marketCycle} loadingCycle={loadingCycle} />
        </TabsContent>

        <TabsContent value="signals">
          <PredictionSignalsTab unifiedAlerts={unifiedAlerts} anomalies={anomalies} anomaliesError={anomaliesError} />
        </TabsContent>

        <TabsContent value="simulation" className="space-y-4">
          <PredictionSimulationTab
            predictions={predictions ?? []}
            whatIfSymbol={whatIfSymbol}
            setWhatIfSymbol={setWhatIfSymbol}
            whatIfChange={whatIfChange}
            setWhatIfChange={setWhatIfChange}
            whatIfResult={whatIfResult}
            whatIfLoading={whatIfLoading}
            runWhatIf={runWhatIf}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
