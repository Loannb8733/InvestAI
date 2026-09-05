import { Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFilDAriane } from '@/components/layout/fil-ariane'
import { LayoutDashboard, FolderOpen, BarChart3, Loader2 } from 'lucide-react'
import { lazyWithRetry } from '@/lib/lazyWithRetry'

const CrowdfundingDashboardPage = lazyWithRetry(() => import('@/pages/CrowdfundingDashboardPage'))
const CrowdfundingProjectsPage = lazyWithRetry(() => import('@/pages/CrowdfundingProjectsPage'))
const CrowdfundingPerformancePage = lazyWithRetry(() => import('@/pages/CrowdfundingPerformancePage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TABS = [
  { value: 'dashboard', label: 'Vue d\'ensemble', icon: LayoutDashboard },
  { value: 'projects', label: 'Projets', icon: FolderOpen },
  { value: 'performance', label: 'Performance', icon: BarChart3 },
] as const

export default function CrowdfundingMesProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'dashboard'

  // Le fil suivait « Mes Projets » quel que soit l'onglet ouvert : il annonçait
  // une page où l'on n'était pas. Il est désormais rendu par le Header, mais
  // c'est toujours ici que le libellé de l'onglet est connu.
  useFilDAriane([
    { label: 'Crowdfunding' },
    { label: TABS.find((t) => t.value === activeTab)?.label ?? "Vue d'ensemble" },
  ])

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'dashboard' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-6">
      {/* Le titre de la page vit ici, pas dans les onglets : ceux-ci sont
          des sections. Masqué à l'œil — le fil d'Ariane et les onglets le
          disent déjà — mais présent pour l'arbre d'accessibilité (UX-02). */}
      <h1 className="sr-only">Crowdfunding</h1>
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full max-w-md grid-cols-3">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="dashboard" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <CrowdfundingDashboardPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="projects" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <CrowdfundingProjectsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="performance" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <CrowdfundingPerformancePage />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}
