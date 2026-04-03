import { Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Zap, Brain, BarChart3, TrendingUp, Bell, Swords, Loader2 } from 'lucide-react'
import Breadcrumb from '@/components/layout/Breadcrumb'
import { lazyWithRetry } from '@/lib/lazyWithRetry'

const InsightsPage = lazyWithRetry(() => import('@/pages/InsightsPage'))
const SmartInsightsPage = lazyWithRetry(() => import('@/pages/SmartInsightsPage'))
const AnalyticsPage = lazyWithRetry(() => import('@/pages/AnalyticsPage'))
const PredictionsPage = lazyWithRetry(() => import('@/pages/PredictionsPage'))
const AlertsPage = lazyWithRetry(() => import('@/pages/AlertsPage'))
const StrategiesPage = lazyWithRetry(() => import('@/pages/StrategiesPage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TABS = [
  { value: 'alpha', label: 'Signaux Alpha', icon: Zap },
  { value: 'smart', label: 'Smart Insights', icon: Brain },
  { value: 'analytics', label: 'Analyses', icon: BarChart3 },
  { value: 'predictions', label: 'Prédictions', icon: TrendingUp },
  { value: 'alerts', label: 'Alertes', icon: Bell },
  { value: 'strategies', label: 'Stratégies', icon: Swords },
] as const

export default function IntelligencePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'alpha'

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'alpha' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: 'Univers Crypto' }, { label: 'Analyses IA' }]} />

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="inline-flex h-10 w-auto overflow-x-auto">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-1.5 px-3 whitespace-nowrap">
              <Icon className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">{label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="alpha" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <InsightsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="smart" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <SmartInsightsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="analytics" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <AnalyticsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="predictions" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <PredictionsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <AlertsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="strategies" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <StrategiesPage />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}
