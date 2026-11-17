import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { PageSkeleton } from '@/components/ui/page-skeleton'
import QueryErrorState from '@/components/ui/query-error-state'
import ImportCSVForm from '@/components/forms/ImportCSVForm'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { useAuthStore } from '@/stores/authStore'
import AddPortfolioDialog from '@/features/portfolio/components/AddPortfolioDialog'
import NoPortfolio from '@/features/portfolio/components/NoPortfolio'
import PortfolioCard from '@/features/portfolio/components/PortfolioCard'
import PortfolioHeader from '@/features/portfolio/components/PortfolioHeader'
import { usePortfolioHistory, usePortfolioList, usePortfolioPerformance, useSparklines } from '@/features/portfolio/hooks'

export default function PortfolioPage() {
  const queryClient = useQueryClient()
  const currency = useAuthStore((s) => s.user?.preferredCurrency || 'EUR')
  const [addingPortfolio, setAddingPortfolio] = useState(false)
  const [importing, setImporting] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('current')

  const list = usePortfolioList()
  const portfolios = useMemo(
    () => list.data?.filter((p) => p.kind !== 'crowdfunding' && p.name.toLowerCase() !== 'crowdfunding') ?? [],
    [list.data]
  )
  const performance = usePortfolioPerformance(selected, currency)
  const history = usePortfolioHistory(selected, currency, activeTab === 'history')
  const sparklines = useSparklines(selected, !!performance.data)

  useEffect(() => {
    if (portfolios.length > 0 && !selected) setSelected(portfolios[0].id)
  }, [portfolios, selected])

  if (list.isLoading) {
    return (
      <PageSkeleton
        titre="Portefeuille"
        description="Le détail de ce que tu possèdes, ligne par ligne."
        niveauTitre={2}
        forme="table"
        action
      />
    )
  }
  if (list.error) {
    return <QueryErrorState error={list.error} onRetry={list.refetch} title="Impossible de charger le portefeuille" />
  }
  if (portfolios.length === 0) return <NoPortfolio />

  const current = portfolios.find((p) => p.id === selected)

  return (
    <div className="space-y-6">
      <PortfolioHeader portfolioId={selected} onImport={() => setImporting(true)} onAddPortfolio={() => setAddingPortfolio(true)} />

      <div className="flex gap-2 flex-wrap">
        {portfolios.map((portfolio) => (
          <Button
            key={portfolio.id}
            variant={selected === portfolio.id ? 'default' : 'outline'}
            onClick={() => setSelected(portfolio.id)}
          >
            {portfolio.name}
          </Button>
        ))}
      </div>

      {current && (
        <PortfolioCard
          key={current.id}
          portfolio={current}
          performance={performance}
          history={history}
          sparklines={sparklines}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onDeleted={() => setSelected(null)}
        />
      )}

      <AddPortfolioDialog open={addingPortfolio} onOpenChange={setAddingPortfolio} />
      <ImportCSVForm
        open={importing}
        onOpenChange={setImporting}
        portfolioId={selected || undefined}
        onSuccess={() => {
          setImporting(false)
          invalidateAllFinancialData(queryClient)
        }}
      />
    </div>
  )
}
