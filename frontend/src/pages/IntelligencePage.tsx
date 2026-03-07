import { lazy, Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Zap, Brain, BarChart3, TrendingUp, Bell, Loader2 } from 'lucide-react'
import Breadcrumb from '@/components/layout/Breadcrumb'

const InsightsPage = lazy(() => import('@/pages/InsightsPage'))
const SmartInsightsPage = lazy(() => import('@/pages/SmartInsightsPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const PredictionsPage = lazy(() => import('@/pages/PredictionsPage'))
const AlertsPage = lazy(() => import('@/pages/AlertsPage'))

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
        <TabsList className="flex w-full max-w-2xl">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-2 flex-1">
              <Icon className="h-4 w-4 hidden sm:block" />
              {label}
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
      </Tabs>
    </div>
  )
}
