import { useMemo, useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import QueryErrorState from '@/components/ui/query-error-state'
import { arrow, formatSignedPercent, gainClass } from '../format'
import { groupPositions, platformShares, UNASSIGNED } from '../grouping'
import { useMoney } from '../hooks'
import type { PortfolioPerformance, PositionGroup, SparklineSeries } from '../types'
import AssetDetailSheet from './AssetDetailSheet'
import CashCards from './CashCards'
import PlatformFilterCard from './PlatformFilterCard'
import type { RowActions } from './PositionRow'
import PositionTable from './PositionTable'

interface PositionsTabProps extends RowActions {
  performance: PortfolioPerformance | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
  cashBalances: Record<string, number>
  sparklines: Record<string, SparklineSeries> | undefined
  onAddAsset: () => void
  onOpenCashBalance: () => void
}

export default function PositionsTab({
  performance,
  loading,
  error,
  onRetry,
  cashBalances,
  sparklines,
  onAddAsset,
  onOpenCashBalance,
  ...actions
}: PositionsTabProps) {
  const money = useMoney()
  const [platformFilter, setPlatformFilter] = useState<string | null>(null)
  const [detailGroup, setDetailGroup] = useState<PositionGroup | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const positions = performance?.assets
  const shares = useMemo(() => platformShares(positions ?? []), [positions])
  const groups = useMemo(() => groupPositions(positions ?? [], platformFilter), [positions, platformFilter])

  if (error) return <QueryErrorState error={error} onRetry={onRetry} title="Impossible de charger les positions" />

  return (
    <>
      <CashCards performance={performance} cashBalances={cashBalances} onOpenCashBalance={onOpenCashBalance} />

      {shares.some((p) => p.platform !== UNASSIGNED) && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
          {shares.map(({ platform, value, assets, gainLoss, roi }) => (
            <PlatformFilterCard key={platform} platform={platform} filter={platformFilter} onFilterChange={setPlatformFilter}>
              <p className="text-lg font-bold">{money(value)}</p>
              <p className={`text-sm font-medium ${gainClass(gainLoss)}`}>
                {arrow(gainLoss)} {money(Math.abs(gainLoss))}
              </p>
              <p className={`text-xs ${roi >= 0 ? 'text-gain/80' : 'text-loss/80'}`}>
                ROI: {formatSignedPercent(roi)}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {assets.length} actif{assets.length > 1 ? 's' : ''}
              </p>
            </PlatformFilterCard>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : groups.length > 0 ? (
        <PositionTable
          groups={groups}
          sparklines={sparklines}
          onOpenDetail={(group) => {
            setDetailGroup(group)
            setDetailOpen(true)
          }}
          {...actions}
        />
      ) : (
        <EmptyState title="Aucun actif dans ce portefeuille" />
      )}
      <div className="mt-4">
        <Button variant="outline" size="sm" onClick={onAddAsset}>
          <Plus className="h-4 w-4 mr-1" />
          Ajouter un actif
        </Button>
      </div>

      <AssetDetailSheet
        open={detailOpen}
        onOpenChange={setDetailOpen}
        group={detailGroup}
        portfolioTotalValue={performance?.total_value}
        sparkline={detailGroup ? sparklines?.[detailGroup.symbol] : undefined}
      />
    </>
  )
}
