import { Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFilDAriane } from '@/components/layout/fil-ariane'
import { Target, Calculator, Loader2 } from 'lucide-react'
import { lazyWithRetry } from '@/lib/lazyWithRetry'

const GoalsPage = lazyWithRetry(() => import('@/pages/GoalsPage'))
const SimulationsPage = lazyWithRetry(() => import('@/pages/SimulationsPage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TAB_LABELS: Record<string, string> = {
  goals: 'Objectifs',
  simulations: 'Simulations',
}

const TABS = [
  { value: 'goals', label: 'Objectifs', icon: Target },
  { value: 'simulations', label: 'Simulations', icon: Calculator },
] as const

export default function StrategyPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'goals'

  useFilDAriane([{ label: 'Outils' }, { label: TAB_LABELS[activeTab] || 'Objectifs' }])

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'goals' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-6">
      {/* « <groupe de menu> › <page> », comme les autres pages. L'ancien premier
          niveau « Stratégie » ne correspondait à aucun groupe ni à aucune page
          (UX-05), et le répéter donnerait « Objectifs › Objectifs ». */}
      {/* Le titre de la page vit ici, pas dans les onglets : ceux-ci sont
          des sections. Masqué à l'œil — le fil d'Ariane et les onglets le
          disent déjà — mais présent pour l'arbre d'accessibilité (UX-02). */}
      <h1 className="sr-only">Objectifs et simulations</h1>
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full max-w-md grid-cols-2">
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
