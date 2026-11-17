import type { HTMLAttributes } from 'react'
import { ArrowRightLeft, ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { arrow, formatQuantity, gainClass } from '../format'
import { weightedBreakeven } from '../grouping'
import type { PositionGroup, SparklineSeries } from '../types'
import PlatformBadge from './PlatformBadge'
import { RiskCell, SparkCell } from './PositionCells'
import type { RowActions } from './PositionRow'

interface PositionGroupRowsProps extends RowActions {
  group: PositionGroup
  sparkline: SparklineSeries | undefined
  rowProps: HTMLAttributes<HTMLTableRowElement>
  expanded: boolean
  onToggle: () => void
}

function GroupCagr({ group }: { group: PositionGroup }) {
  const withCagr = group.assets.filter((a) => a.annualized_return != null && a.holding_days != null && a.holding_days >= 7)
  if (withCagr.length === 0) return null
  const coveredInvested = withCagr.reduce((s, a) => s + a.total_invested, 0)
  const coverage = group.totalInvested > 0 ? coveredInvested / group.totalInvested : 0
  if (coveredInvested <= 0 || coverage < 0.9) {
    return (
      <p className="text-[10px] text-muted-foreground mt-0.5" title="CAGR indisponible pour toutes les plateformes">
        CAGR: —
      </p>
    )
  }
  const weightedCagr = withCagr.reduce((s, a) => s + (a.annualized_return ?? 0) * a.total_invested, 0) / coveredInvested
  return (
    <p className="text-[10px] text-muted-foreground mt-0.5" title="Pondéré par le capital investi">
      CAGR: {weightedCagr >= 0 ? '+' : ''}{weightedCagr.toFixed(1)}%/an
    </p>
  )
}

export default function PositionGroupRows({ group, sparkline, rowProps, expanded, onToggle, ...actions }: PositionGroupRowsProps) {
  return (
    <>
      <tr
        className="border-b cursor-pointer hover:bg-muted/30 transition-colors focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-ring"
        {...rowProps}
      >
        <td className="py-3 text-center">
          <div className="flex justify-center items-center gap-1">
            <AssetIconCompact symbol={group.symbol} name={group.name ?? undefined} assetType={group.asset_type} size={36} />
          </div>
        </td>
        <td className="text-center py-3">
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-expanded={expanded}
            aria-label={`${expanded ? 'Masquer' : 'Afficher'} les positions par plateforme de ${group.symbol}`}
            onClick={(e) => {
              e.stopPropagation()
              onToggle()
            }}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            <span>{group.assets.length} plateformes</span>
          </button>
        </td>
        <td className="text-center py-3 font-medium">{formatQuantity(group.totalQuantity)}</td>
        <td className="text-center py-3 text-muted-foreground">
          <span title={`PRA hors frais : ${group.avgBuyPrice > 0 ? formatCurrency(group.avgBuyPrice) : '-'}`}>
            {formatCurrency(weightedBreakeven(group.assets))}
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
            <GroupCagr group={group} />
          </div>
        </td>
        <RiskCell weight={group.assets[0].risk_weight} className="py-3" />
        <SparkCell series={sparkline} className="py-3" />
        <td className="text-center py-3" />
      </tr>
      {expanded &&
        group.assets.map((asset) => (
          <tr key={asset.id} className="border-b last:border-0 bg-muted/20">
            <td className="py-2 text-center" />
            <td className="text-center py-2">
              <PlatformBadge asset={asset} onChange={actions.onUpdateAssetExchange} />
            </td>
            <td className="text-center py-2 text-sm">{formatQuantity(asset.quantity)}</td>
            <td className="text-center py-2 text-sm text-muted-foreground">
              <span title={`PRA hors frais : ${asset.avg_buy_price > 0 ? formatCurrency(asset.avg_buy_price) : '-'}`}>
                {formatCurrency(asset.breakeven_price)}
              </span>
            </td>
            <td className="text-center py-2 text-sm">{asset.current_price ? formatCurrency(asset.current_price) : '-'}</td>
            <td className="text-center py-2 text-sm">{formatCurrency(asset.current_value)}</td>
            <td className={`text-center py-2 text-sm ${gainClass(asset.gain_loss)}`}>
              {arrow(asset.gain_loss)} {formatCurrency(asset.gain_loss)}
            </td>
            <RiskCell weight={asset.risk_weight} className="py-2" />
            <SparkCell series={sparkline} className="py-2" />
            <td className="text-center py-2">
              <div className="flex justify-center gap-1">
                <Button variant="ghost" size="icon" className="h-7 w-7 tap-target" onClick={() => actions.onAddTransaction(asset.id, asset.symbol)} title="Ajouter une transaction">
                  <ArrowRightLeft className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 tap-target" onClick={() => actions.onDeleteAsset(asset)} title="Supprimer">
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            </td>
          </tr>
        ))}
    </>
  )
}
