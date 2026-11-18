import { useState } from 'react'
import { History, Loader2, PiggyBank, TrendingDown, TrendingUp } from 'lucide-react'
import EmptyState from '@/components/ui/empty-state'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import SpotlightGroup from '@/components/ui/spotlight-group'
import StatCard from '@/components/ui/stat-card'
import QueryErrorState from '@/components/ui/query-error-state'
import { platformOf, soldPlatforms } from '../grouping'
import { useMoney } from '../hooks'
import type { PortfolioHistory, SoldAsset } from '../types'
import PlatformFilterCard from './PlatformFilterCard'
import SoldAssetsTable from './SoldAssetsTable'

interface HistoryTabProps {
  history: PortfolioHistory | undefined
  loading: boolean
  stale: boolean
  error: unknown
  onRetry: () => void
}

function HistorySummary({ history }: { history: PortfolioHistory }) {
  const money = useMoney()
  const gained = history.realized_gains >= 0
  return (
    <SpotlightGroup className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <StatCard className="spot-card" label="Total investi (historique)" icon={PiggyBank} value={history.total_invested_all_time} format={money} />
      <StatCard className="spot-card" label="Total vendu" icon={TrendingUp} value={history.total_sold} format={money} />
      <StatCard className="spot-card" label="Frais totaux" icon={History} value={history.total_fees} format={money} />
      <StatCard
        className={`spot-card ${gained ? '[&_.font-serif]:text-gain' : '[&_.font-serif]:text-loss'}`}
        label="Gains réalisés"
        icon={gained ? TrendingUp : TrendingDown}
        value={history.realized_gains}
        format={money}
      />
    </SpotlightGroup>
  )
}

function SoldAssets({ soldAssets }: { soldAssets: SoldAsset[] }) {
  const money = useMoney()
  const [filter, setFilter] = useState<string | null>(null)
  const shown = soldAssets.filter((asset) => !filter || platformOf(asset.exchange) === filter)
  return (
    <div>
      <h3 className="text-lg font-semibold mb-3">
        Actifs vendus ({new Set(shown.map((a) => a.symbol)).size})
      </h3>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
        {soldPlatforms(soldAssets).map(([platform, data]) => (
          <PlatformFilterCard key={platform} platform={platform} filter={filter} onFilterChange={setFilter}>
            <p className="text-lg font-bold">{money(data.value)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {data.count} actif{data.count > 1 ? 's' : ''}
            </p>
          </PlatformFilterCard>
        ))}
      </div>
      <SoldAssetsTable soldAssets={shown} />
    </div>
  )
}

export default function HistoryTab({ history, loading, stale, error, onRetry }: HistoryTabProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SkeletonStatCard />
        <SkeletonStatCard />
        <SkeletonStatCard />
        <SkeletonStatCard />
      </div>
    )
  }
  if (error) return <QueryErrorState error={error} onRetry={onRetry} title="Impossible de charger l'historique" />
  if (!history) return <EmptyState title="Aucune donnée historique" />
  return (
    <div className={`space-y-6 ${stale ? 'opacity-50 pointer-events-none' : ''}`}>
      {stale && (
        <div className="flex items-center justify-center py-2">
          <Loader2 className="h-4 w-4 animate-spin text-primary mr-2" />
          <span className="text-sm text-muted-foreground">Chargement...</span>
        </div>
      )}
      <HistorySummary history={history} />
      {history.sold_assets.length > 0 ? (
        <SoldAssets soldAssets={history.sold_assets} />
      ) : (
        <EmptyState title="Aucun actif vendu" />
      )}
    </div>
  )
}
