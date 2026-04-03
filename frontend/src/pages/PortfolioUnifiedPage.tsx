import { Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Wallet, ArrowRightLeft, Link2, Loader2 } from 'lucide-react'
import Breadcrumb from '@/components/layout/Breadcrumb'
import { lazyWithRetry } from '@/lib/lazyWithRetry'

const PortfolioPage = lazyWithRetry(() => import('@/pages/PortfolioPage'))
const TransactionsPage = lazyWithRetry(() => import('@/pages/TransactionsPage'))
const ExchangesPage = lazyWithRetry(() => import('@/pages/ExchangesPage'))

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-[40vh]">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

const TABS = [
  { value: 'resume', label: 'Résumé', icon: Wallet },
  { value: 'transactions', label: 'Transactions', icon: ArrowRightLeft },
  { value: 'exchanges', label: 'Exchanges', icon: Link2 },
] as const

export default function PortfolioUnifiedPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') || 'resume'

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'resume' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: 'Univers Crypto' }, { label: 'Portefeuille' }]} />

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full max-w-md grid-cols-3">
          {TABS.map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="resume" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <PortfolioPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="transactions" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <TransactionsPage />
          </Suspense>
        </TabsContent>

        <TabsContent value="exchanges" className="mt-6">
          <Suspense fallback={<TabLoader />}>
            <ExchangesPage />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  )
}
