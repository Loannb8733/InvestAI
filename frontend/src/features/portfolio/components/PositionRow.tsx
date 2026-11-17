import type { HTMLAttributes } from 'react'
import { ArrowRightLeft, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { arrow, formatQuantity, gainClass } from '../format'
import type { Position, PositionGroup, SparklineSeries } from '../types'
import PlatformBadge from './PlatformBadge'
import { RiskCell, SparkCell } from './PositionCells'

export interface RowActions {
  onAddTransaction: (assetId: string, assetSymbol: string) => void
  onDeleteAsset: (asset: Position) => void
  onUpdateAssetExchange: (assetId: string, exchange: string | null) => void
}

interface PositionRowProps extends RowActions {
  group: PositionGroup
  sparkline: SparklineSeries | undefined
  rowProps: HTMLAttributes<HTMLTableRowElement>
}

const holdingLabel = (days: number) => (days < 365 ? `${days}j` : `${(days / 365.25).toFixed(1)}a`)

export default function PositionRow({ group, sparkline, rowProps, ...actions }: PositionRowProps) {
  const asset = group.assets[0]
  const days = asset.holding_days
  return (
    <tr
      className="border-b last:border-0 cursor-pointer hover:bg-muted/30 transition-colors focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-ring"
      {...rowProps}
    >
      <td className="py-3 text-center">
        <div className="flex justify-center">
          <AssetIconCompact symbol={group.symbol} name={group.name ?? undefined} assetType={group.asset_type} size={36} />
        </div>
      </td>
      <td className="text-center py-3" onClick={(e) => e.stopPropagation()}>
        <PlatformBadge asset={asset} onChange={actions.onUpdateAssetExchange} />
      </td>
      <td className="text-center py-3">{formatQuantity(group.totalQuantity)}</td>
      <td className="text-center py-3 text-muted-foreground">
        <span title={`PRA hors frais : ${group.avgBuyPrice > 0 ? formatCurrency(group.avgBuyPrice) : '-'}`}>
          {formatCurrency(asset.breakeven_price)}
        </span>
      </td>
      <td className="text-center py-3">{group.currentPrice ? formatCurrency(group.currentPrice) : '-'}</td>
      <td className="text-center py-3 font-medium">{formatCurrency(group.totalValue)}</td>
      <td className={`text-center py-3 ${gainClass(group.totalGainLoss)}`}>
        <div>
          <p>{arrow(group.totalGainLoss)} {formatCurrency(group.totalGainLoss)}</p>
          <p className="text-xs">
            {arrow(group.totalGainLoss)}{' '}
            {formatPercent(group.totalGainLossPercent)}
          </p>
          {asset.annualized_return != null && days != null && days >= 7 && (
            <p className="text-[10px] text-muted-foreground mt-0.5" title={`Détenu depuis ${days}j`}>
              CAGR: {asset.annualized_return >= 0 ? '+' : ''}{asset.annualized_return.toFixed(1)}%/an
              {' '}({holdingLabel(days)})
            </p>
          )}
        </div>
      </td>
      <RiskCell weight={asset.risk_weight} className="py-3" />
      <SparkCell series={sparkline} className="py-3" />
      <td className="text-center py-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => actions.onAddTransaction(asset.id, group.symbol)} title="Ajouter une transaction">
            <ArrowRightLeft className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => actions.onDeleteAsset(asset)} title="Supprimer">
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </td>
    </tr>
  )
}
