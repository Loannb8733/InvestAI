import { lazy, Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Target, Calculator, Loader2 } from 'lucide-react'
import Breadcrumb from '@/components/layout/Breadcrumb'

const GoalsPage = lazy(() => import('@/pages/GoalsPage'))
const SimulationsPage = lazy(() => import('@/pages/SimulationsPage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TABS = [
  { value: 'goals', label: 'Objectifs', icon: Target },
  { value: 'simulations', label: 'Simulations', icon: Calculator },
] as const

export default function StrategyPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'goals'

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'goals' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: 'Stratégie' }, { label: activeTab === 'goals' ? 'Objectifs' : 'Simulations' }]} />

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full max-w-sm grid-cols-2">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="goals" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <GoalsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="simulations" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <SimulationsPage />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}
