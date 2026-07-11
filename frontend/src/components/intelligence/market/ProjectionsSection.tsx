import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import EmptyState from '@/components/ui/empty-state'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { formatCurrency } from '@/lib/utils'
import type { usePredictionData, AccuracyReport } from '@/hooks/usePredictionData'
import PredictionListView from '@/components/predictions/PredictionListView'
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  ChevronDown,
  Gauge,
  Loader2,
} from 'lucide-react'

/**
 * Section « Projections » du pilier Marché & Signaux.
 *
 * Reprend l'onglet Projections de l'ancienne page Prédictions :
 * prévision portefeuille, prédictions par actif (avec toggle réalité),
 * badge de confiance honnête basé sur le hit-rate réel, encart de précision
 * et rapport d'accuracy complet (« Précision du modèle »).
 */

interface ProjectionsSectionProps {
  pd: ReturnType<typeof usePredictionData>
}

export default function ProjectionsSection({ pd }: ProjectionsSectionProps) {
  const {
    daysAhead, setDaysAhead,
    selectedAsset, setSelectedAsset,
    showReality, setShowReality,
    predictions, summary, dt,
    backtestData, loadingBacktest,
    selectedPrediction, chartData, showSupportResistance,
    modelAccuracy, accuracyReport,
    formatPrice,
  } = pd

  return (
    <div className="space-y-4">
      {/* Contrôles : badge de confiance honnête + horizon */}
      <div className="flex items-center justify-end gap-2 flex-wrap">
        {/* Badge de confiance basé sur le track-record réel du modèle
            (direction correcte en backtest), pas sur l'horizon choisi. */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex cursor-help">
                <Badge
                  variant={modelAccuracy.level === 'high' ? 'default' : modelAccuracy.level === 'medium' ? 'secondary' : 'outline'}
                  className="text-xs"
                >
                  Confiance : {modelAccuracy.level === 'high' ? 'Haute' : modelAccuracy.level === 'medium' ? 'Modérée' : 'Indicative'}
                </Badge>
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              {modelAccuracy.hitRate != null ? (
                <>
                  <p className="text-xs font-medium">Précision historique du modèle</p>
                  <p className="text-xs mt-1">
                    Direction correcte : {modelAccuracy.hitRate.toFixed(0)} %
                    {modelAccuracy.mape != null && <> · MAPE : {modelAccuracy.mape.toFixed(1)} %</>}
                    {modelAccuracy.source === 'predictions' && <> (moyenne par actif)</>}
                  </p>
                  {modelAccuracy.level === 'low' && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Précision historique insuffisante (moins de 50 % de directions correctes).
                    </p>
                  )}
                </>
              ) : (
                <p className="text-xs">
                  Précision historique insuffisante — pas encore assez de prédictions vérifiées pour évaluer le modèle.
                </p>
              )}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
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

      {/* Prévision portefeuille */}
      <Card elevation="raised">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-5 w-5 text-primary" />
            <span className="font-semibold">Prévision portefeuille</span>
            <span className="text-xs text-muted-foreground ml-auto">{summary?.days_ahead ?? daysAhead}j</span>
          </div>
          {summary ? (
            <div className="space-y-4">
              <div className="text-center">
                <div className={`text-4xl font-serif font-medium flex items-center justify-center gap-2 ${summary.expected_change_percent >= 0 ? 'text-gain' : 'text-loss'}`}>
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
                      {summary.bullish_assets > 0 && <div className="bg-gain transition-all" style={{ width: `${(summary.bullish_assets / total) * 100}%` }} />}
                      {summary.neutral_assets > 0 && <div className="bg-warning transition-all" style={{ width: `${(summary.neutral_assets / total) * 100}%` }} />}
                      {summary.bearish_assets > 0 && <div className="bg-loss transition-all" style={{ width: `${(summary.bearish_assets / total) * 100}%` }} />}
                    </div>
                  ) : <div className="flex h-3 rounded-full overflow-hidden bg-muted" />
                })()}
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gain" />{summary.bullish_assets} haussier</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-warning" />{summary.neutral_assets} neutre</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-loss" />{summary.bearish_assets} baissier</span>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">Aucune donnée</p>
          )}
        </CardContent>
      </Card>

      {/* Encart précision (backtest) */}
      {(modelAccuracy.mape != null || modelAccuracy.backtestHitRate != null) && (
        <div className="rounded-lg border bg-muted/40 p-3 flex items-center gap-2 text-sm">
          <Gauge className="h-4 w-4 text-primary shrink-0" />
          <span>
            Précision du modèle (backtest {daysAhead}j) :
            {modelAccuracy.mape != null && <> MAPE {modelAccuracy.mape.toFixed(1)} %</>}
            {modelAccuracy.mape != null && modelAccuracy.backtestHitRate != null && ' · '}
            {modelAccuracy.backtestHitRate != null && <>direction correcte {modelAccuracy.backtestHitRate.toFixed(0)} %</>}
          </span>
        </div>
      )}

      {/* Prédictions par actif + rapport d'accuracy */}
      {predictions && predictions.length > 0 ? (
        <>
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
          <ModelAccuracySection report={accuracyReport} loading={loadingBacktest} />
        </>
      ) : (
        <EmptyState
          icon={BarChart3}
          title="Pas encore de projection"
          description="Ajoute des actifs à ton portefeuille pour que l'analyse statistique puisse dessiner les scénarios à venir."
        />
      )}
    </div>
  )
}

// ── Précision du modèle (rapport d'accuracy) ─────────────────────────
// Section honnête : montre le track-record réel du modèle, actif par actif,
// sans jamais promettre de « précision garantie ».

const MIN_SAMPLES = 10

function directionColor(hitRate: number | null): string {
  if (hitRate == null) return 'text-muted-foreground'
  if (hitRate >= 60) return 'text-gain'
  if (hitRate >= 50) return 'text-warning'
  return 'text-loss'
}

function honestSummary(direction: number | null, nVerified: number): string {
  if (direction == null || nVerified === 0) {
    return "Pas encore assez de prédictions vérifiées pour évaluer la fiabilité directionnelle du modèle sur ce portefeuille."
  }
  if (direction < 55) {
    return "Les prédictions directionnelles de ce portefeuille sont proches du hasard — à utiliser comme contexte, pas comme signal."
  }
  if (direction >= 60) {
    return `Le modèle a correctement anticipé la direction dans ${direction.toFixed(0)} % des cas sur l'historique vérifié — un résultat encourageant, à interpréter avec mesure : l'historique passé ne préjuge pas des performances futures.`
  }
  return `Avec ${direction.toFixed(0)} % de directions correctes, le modèle fait légèrement mieux que le hasard — prudence dans l'interprétation.`
}

function ModelAccuracySection({ report, loading }: { report: AccuracyReport; loading: boolean }) {
  const [open, setOpen] = useState(false)

  return (
    <Card elevation="raised">
      <CardContent className="pt-4 pb-4">
        <button
          type="button"
          className="w-full flex items-center justify-between gap-2 text-left"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
        >
          <span className="flex items-center gap-2 font-semibold">
            <Gauge className="h-5 w-5 text-primary" />
            Précision du modèle
            <span className="text-xs font-normal text-muted-foreground">
              — historique vérifié, pas une garantie
            </span>
          </span>
          <span className="flex items-center gap-2">
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
          </span>
        </button>

        {open && (
          <div className="mt-4 space-y-4">
            {/* Agrégats backtest */}
            <div className="rounded-lg border bg-muted/40 p-3 space-y-2">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                <span>
                  MAPE global :{' '}
                  <span className="font-medium">
                    {report.overallMape != null ? `${report.overallMape.toFixed(1)} %` : '—'}
                  </span>
                </span>
                <span>
                  Direction correcte :{' '}
                  <span className={`font-medium ${directionColor(report.overallDirection)}`}>
                    {report.overallDirection != null ? `${report.overallDirection.toFixed(0)} %` : '—'}
                  </span>
                </span>
                <span>
                  Prédictions vérifiées :{' '}
                  <span className="font-medium">{report.nVerified}</span>
                </span>
                <span>
                  Période : <span className="font-medium">prédictions à {report.horizonDays} j vérifiées à échéance</span>
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {honestSummary(report.overallDirection, report.nVerified)}
              </p>
            </div>

            {/* Tableau par actif */}
            {report.rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="text-left py-2 px-2 text-xs font-medium">Actif</th>
                      <th scope="col" className="text-right py-2 px-2 text-xs font-medium">Direction correcte</th>
                      <th scope="col" className="text-right py-2 px-2 text-xs font-medium">MAPE</th>
                      <th scope="col" className="text-right py-2 px-2 text-xs font-medium">Skill score</th>
                      <th scope="col" className="text-right py-2 px-2 text-xs font-medium">Échantillons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map(row => {
                      const insufficient = row.nSamples < MIN_SAMPLES
                      return (
                        <tr
                          key={row.symbol}
                          className={`border-b last:border-0 ${insufficient ? 'opacity-50' : ''}`}
                        >
                          <td className="py-2 px-2">
                            <span className="font-medium">{row.symbol}</span>
                            {insufficient && (
                              <Badge variant="outline" className="ml-2 text-[10px] px-1.5 py-0 text-muted-foreground">
                                échantillon insuffisant
                              </Badge>
                            )}
                          </td>
                          <td className={`py-2 px-2 text-right tabular-nums font-medium ${insufficient ? 'text-muted-foreground' : directionColor(row.hitRate)}`}>
                            {row.hitRate != null ? `${row.hitRate.toFixed(0)} %` : '—'}
                          </td>
                          <td className="py-2 px-2 text-right tabular-nums">
                            {row.mape != null ? `${row.mape.toFixed(1)} %` : '—'}
                          </td>
                          <td className="py-2 px-2 text-right tabular-nums">
                            {row.skillScore != null ? row.skillScore.toFixed(0) : '—'}
                          </td>
                          <td className="py-2 px-2 text-right tabular-nums text-muted-foreground">
                            {row.nSamples}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Aucune métrique par actif disponible.</p>
            )}

            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Direction correcte : % de prédictions dont le sens (hausse/baisse) s'est vérifié.
              MAPE : erreur moyenne absolue en % entre prix prédit et prix réel.
              Skill score : performance relative à une prévision naïve (50 = équivalent, 100 = parfait).
              Les lignes avec moins de {MIN_SAMPLES} échantillons sont grisées : trop peu de données pour conclure.
              Ces chiffres décrivent le passé — ils ne préjugent en rien des performances futures.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
