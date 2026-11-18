import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { arrow, formatHoldingPeriod, formatQuantity, gainClass } from '../format'
import { groupSoldAssets } from '../grouping'
import { useMoney } from '../hooks'
import type { SoldAsset } from '../types'

const COLUMNS = ['Actif', 'Plateforme', 'Qté achetée', 'Total investi', 'Qté vendue', 'Total vendu', '+/- Réalisé', 'Détention']

function SoldCells({ asset, pad, text }: { asset: SoldAsset; pad: string; text: string }) {
  const money = useMoney()
  const cell = `${pad}${text}`
  return (
    <>
      <td className={`text-center ${pad}`}>
        <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{asset.exchange || '-'}</span>
      </td>
      <td className={`text-center ${cell}`}>{formatQuantity(asset.total_bought)}</td>
      <td className={`text-center ${cell}`}>{money(asset.total_bought_value)}</td>
      <td className={`text-center ${cell}`}>{formatQuantity(asset.total_sold)}</td>
      <td className={`text-center ${cell}`}>{money(asset.total_sold_value)}</td>
      <td className={`text-center ${cell} ${gainClass(asset.realized_gain)}`}>
        {arrow(asset.realized_gain)} {money(asset.realized_gain)}
      </td>
      <td className={`text-center ${pad} text-xs text-muted-foreground whitespace-nowrap`}>
        {formatHoldingPeriod(asset.first_transaction, asset.last_transaction)}
      </td>
    </>
  )
}

export default function SoldAssetsTable({ soldAssets }: { soldAssets: SoldAsset[] }) {
  const money = useMoney()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const toggle = (symbol: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b">
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groupSoldAssets(soldAssets).map((group) => {
            if (group.assets.length === 1) {
              const asset = group.assets[0]
              return (
                <tr key={asset.id} className="border-b last:border-0">
                  <td className="py-3 text-center">
                    <div className="flex justify-center">
                      <AssetIconCompact symbol={asset.symbol} name={asset.name ?? undefined} assetType={asset.asset_type} size={36} />
                    </div>
                  </td>
                  <SoldCells asset={asset} pad="py-3" text="" />
                </tr>
              )
            }
            const isExpanded = expanded.has(group.symbol)
            return (
              <Fragment key={group.symbol}>
                <tr className="border-b cursor-pointer hover:bg-muted/30 transition-colors" onClick={() => toggle(group.symbol)}>
                  <td className="py-3 text-center">
                    <div className="flex justify-center">
                      <AssetIconCompact symbol={group.symbol} name={group.name ?? undefined} assetType={group.asset_type} size={36} />
                    </div>
                  </td>
                  <td className="text-center py-3">
                    <div className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      <span>{group.assets.length} plateformes</span>
                    </div>
                  </td>
                  <td className="text-center py-3 font-medium">{formatQuantity(group.totalBought)}</td>
                  <td className="text-center py-3 font-medium">{money(group.totalBoughtValue)}</td>
                  <td className="text-center py-3 font-medium">{formatQuantity(group.totalSold)}</td>
                  <td className="text-center py-3 font-medium">{money(group.totalSoldValue)}</td>
                  <td className={`text-center py-3 font-medium ${gainClass(group.realizedGain)}`}>
                    {arrow(group.realizedGain)} {money(group.realizedGain)}
                  </td>
                  <td className="text-center py-3 text-xs text-muted-foreground whitespace-nowrap">
                    {formatHoldingPeriod(group.firstTx, group.lastTx)}
                  </td>
                </tr>
                {isExpanded &&
                  group.assets.map((asset) => (
                    <tr key={asset.id} className="border-b last:border-0 bg-muted/20">
                      <td className="py-2 text-center" />
                      <SoldCells asset={asset} pad="py-2" text=" text-sm" />
                    </tr>
                  ))}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
