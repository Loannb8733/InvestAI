import { Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ShieldHalf, Radar, Crosshair, Bell, Loader2 } from 'lucide-react'
import Breadcrumb from '@/components/layout/Breadcrumb'
import RegimeHeader from '@/components/intelligence/RegimeHeader'
import { lazyWithRetry } from '@/lib/lazyWithRetry'

/**
 * Hub Intelligence — architecture « 3 piliers » (refonte 2026-07).
 *
 * Avant : 6 onglets-pages juxtaposés (Signaux Alpha, Smart Insights,
 * Analyses, Prédictions, Alertes, Stratégies) avec 4 moteurs de
 * recommandation concurrents, le régime de marché affiché 5 fois et les
 * mêmes métriques calculées sur des fenêtres différentes selon l'onglet.
 *
 * Après :
 *   - Risque & Performance  = Analytics + Smart Insights (une seule fenêtre
 *     de calcul, métriques dédupliquées, les 2 moteurs d'optimisation
 *     côte à côte et étiquetés) ;
 *   - Marché & Signaux      = Prédictions + Cycles + Alpha/matrice +
 *     anomalies + rapport d'accuracy ;
 *   - Décisions             = ordres planifiés + stratégies + P&L — l'unique
 *     endroit où l'on agit ;
 *   - Alertes               (outil, inchangé).
 * Le régime de marché est affiché UNE fois, dans le RegimeHeader partagé.
 * Frais / TLH / Revenus passifs / Backtest DCA ont migré vers
 * Rapports › Optimisations.
 */

const RiskPerformancePillar = lazyWithRetry(() => import('@/components/intelligence/RiskPerformancePillar'))
const MarketSignalsPillar = lazyWithRetry(() => import('@/components/intelligence/MarketSignalsPillar'))
const DecisionsPillar = lazyWithRetry(() => import('@/components/intelligence/DecisionsPillar'))
const AlertsPage = lazyWithRetry(() => import('@/pages/AlertsPage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TABS = [
  { value: 'risk', label: 'Risque & Performance', icon: ShieldHalf },
  { value: 'market', label: 'Marché & Signaux', icon: Radar },
  { value: 'decisions', label: 'Décisions', icon: Crosshair },
  { value: 'alerts', label: 'Alertes', icon: Bell },
] as const

/** Anciens ?tab= (liens externes, favoris) → nouveaux piliers. */
const LEGACY_TAB_MAP: Record<string, string> = {
  alpha: 'market',
  smart: 'risk',
  analytics: 'risk',
  predictions: 'market',
  strategies: 'decisions',
  alerts: 'alerts',
}

export default function IntelligencePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab') || 'risk'
  const activeTab = TABS.some((t) => t.value === rawTab) ? rawTab : (LEGACY_TAB_MAP[rawTab] ?? 'risk')

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'risk' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: 'Univers Crypto' }, { label: 'Analyses IA' }]} />

      {/* Le régime de marché, UNE fois pour tout le hub. */}
      <RegimeHeader />

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="inline-flex h-10 w-auto overflow-x-auto">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-1.5 px-3 whitespace-nowrap">
              <Icon className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">{label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="risk" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <RiskPerformancePillar />
          </Suspense>
        </TabsContent>

        <TabsContent value="market" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <MarketSignalsPillar />
          </Suspense>
        </TabsContent>

        <TabsContent value="decisions" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <DecisionsPillar />
          </Suspense>
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <AlertsPage />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}
