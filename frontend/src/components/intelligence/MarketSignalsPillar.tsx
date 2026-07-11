import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { usePredictionData } from '@/hooks/usePredictionData'
import CycleContextSection from './market/CycleContextSection'
import ProjectionsSection from './market/ProjectionsSection'
import AlphaSignalsSection from './market/AlphaSignalsSection'
import AnomaliesSection from './market/AnomaliesSection'
import {
  AlertTriangle,
  BarChart3,
  Loader2,
  Repeat,
  Zap,
} from 'lucide-react'

/**
 * Pilier « Marché & Signaux » du hub Intelligence (refonte 3 piliers).
 *
 * Fusion de PredictionsPage + les sections SIGNAUX d'InsightsPage :
 *   1. Cycle & contexte — phase de cycle détaillée, sentiment, signaux de
 *      marché, régimes par actif, événements à venir (CycleContextSection).
 *   2. Projections — prédictions par actif, prévision portefeuille, toggle
 *      réalité, badge de confiance honnête (ProjectionsSection).
 *   3. Rapport d'accuracy — « Précision du modèle » complet (dans Projections).
 *   4. Signaux Alpha — score Alpha, matrice de stratégie, validation Monte
 *      Carlo (AlphaSignalsSection).
 *   5. Anomalies — source unique Smart Insights, chiffrée en EUR
 *      (AnomaliesSection).
 *
 * Choix d'organisation : sous-tabs internes légers plutôt que sections
 * empilées — le contenu cumulé (cycles + projections + alpha + anomalies)
 * dépasserait 6 écrans de scroll ; les onglets reprennent le modèle mental
 * des anciennes pages et React Query rend la bascule instantanée (les
 * queries partagées restent montées via usePredictionData).
 *
 * Supprimé volontairement par rapport aux sources :
 * - Les grandes bannières de régime prescriptives de PredictionsPage
 *   (« Mode Accumulation », « sécurisez 20-30 % »…) et les bandeaux de
 *   régime de la Matrice de Stratégie : le régime vit dans RegimeHeader
 *   (partagé) ; la recommandation actionnable devient la carte compacte
 *   « Suggestion de posture » (PostureSuggestionCard, étiquetée confiance).
 * - L'onglet « Simulation » (what-if) de PredictionsPage : doublon de
 *   SimulationsPage, il disparaît avec la refonte.
 * - Les onglets Frais / Tax-Loss / Revenus passifs / Backtest DCA
 *   d'InsightsPage : ils migrent vers le pilier Rapports.
 *
 * Note : ce composant n'affiche ni <h1> ni Breadcrumb (gérés par le hub) et
 * n'est pas encore branché dans IntelligencePage (intégration séparée).
 */
export default function MarketSignalsPillar() {
  const pd = usePredictionData()

  if (pd.loadingPredictions || pd.loadingSentiment) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Disclaimer — analyse exploratoire, pas un conseil */}
      <div className="rounded-lg border border-warning/30 bg-warning/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-warning mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-warning dark:text-warning">Analyse exploratoire</p>
          <p className="text-xs text-muted-foreground mt-1">
            Ces projections sont basées sur des modèles statistiques appliqués aux prix historiques.
            Elles ne constituent pas des conseils d'investissement. Les marchés crypto sont hautement
            imprévisibles — aucun modèle ne peut prédire l'avenir de manière fiable.
          </p>
        </div>
      </div>

      <Tabs defaultValue="cycle" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="cycle" className="flex items-center gap-2">
            <Repeat className="h-4 w-4" />
            <span className="hidden sm:inline">Cycle & contexte</span>
            <span className="sm:hidden">Cycle</span>
            {pd.highAlerts > 0 && (
              <span className="ml-1 w-5 h-5 rounded-full bg-loss text-white text-xs flex items-center justify-center">
                {pd.highAlerts}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="projections" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />Projections
          </TabsTrigger>
          <TabsTrigger value="alpha" className="flex items-center gap-2">
            <Zap className="h-4 w-4" />
            <span className="hidden sm:inline">Signaux Alpha</span>
            <span className="sm:hidden">Alpha</span>
          </TabsTrigger>
          <TabsTrigger value="anomalies" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />Anomalies
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cycle">
          <CycleContextSection pd={pd} />
        </TabsContent>

        <TabsContent value="projections">
          <ProjectionsSection pd={pd} />
        </TabsContent>

        <TabsContent value="alpha">
          <AlphaSignalsSection />
        </TabsContent>

        <TabsContent value="anomalies">
          <AnomaliesSection />
        </TabsContent>
      </Tabs>
    </div>
  )
}
