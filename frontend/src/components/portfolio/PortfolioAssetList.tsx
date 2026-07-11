import { Fragment, useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { formatCurrency, formatPercent } from '@/lib/utils'
import {
  Plus,
  Loader2,
  Trash2,
  ArrowRightLeft,
  Banknote,
  Shield,
  Building2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import EmptyState from '@/components/ui/empty-state'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { ALL_PLATFORMS, isColdWallet } from '@/lib/platforms'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Sparkline } from '@/components/ui/sparkline'
import AssetDetailSheet from '@/components/portfolio/AssetDetailSheet'
import type { AssetMetrics, PortfolioMetrics } from '@/types'

interface GroupedAsset {
  symbol: string
  name?: string
  asset_type: string
  assets: AssetMetrics[]
  totalQuantity: number
  totalValue: number
  totalInvested: number
  totalGainLoss: number
  totalGainLossPercent: number
  currentPrice?: number
  avgBuyPrice: number
  isMultiPlatform: boolean
}

interface PortfolioAssetListProps {
  portfolioMetrics: PortfolioMetrics | undefined
  loadingMetrics: boolean
  cashBalances: Record<string, number>
  portfolioId: string
  portfolioName: string
  sparklines?: Record<string, { prices: number[]; change_pct: number }>
  onAddAsset: (portfolioId: string, portfolioName: string) => void
  onAddTransaction: (assetId: string, assetSymbol: string) => void
  onDeleteAsset: (asset: AssetMetrics) => void
  onOpenCashBalance: () => void
  onUpdateAssetExchange?: (assetId: string, exchange: string | null) => void
}

export default function PortfolioAssetList({
  portfolioMetrics,
  loadingMetrics,
  cashBalances,
  portfolioId,
  portfolioName,
  sparklines,
  onAddAsset,
  onAddTransaction,
  onDeleteAsset,
  onOpenCashBalance,
  onUpdateAssetExchange,
}: PortfolioAssetListProps) {
  const [platformPopover, setPlatformPopover] = useState<string | null>(null)
  const [platformFilter, setPlatformFilter] = useState<string | null>(null)
  const [expandedSymbols, setExpandedSymbols] = useState<Set<string>>(new Set())
  // Vue détail : le groupe reste monté pendant l'animation de fermeture.
  const [detailGroup, setDetailGroup] = useState<GroupedAsset | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  // Reset filters when portfolio changes
  useEffect(() => {
    setPlatformFilter(null)
    setExpandedSymbols(new Set())
    setDetailOpen(false)
  }, [portfolioId])

  const openDetail = (group: GroupedAsset) => {
    setDetailGroup(group)
    setDetailOpen(true)
  }

  const detailRowProps = (group: GroupedAsset) => ({
    role: 'button' as const,
    tabIndex: 0,
    'aria-label': `Voir le détail de ${group.symbol}`,
    onClick: () => openDetail(group),
    onKeyDown: (e: KeyboardEvent<HTMLTableRowElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        openDetail(group)
      }
    },
  })

  const toggleExpanded = (symbol: string) => {
    setExpandedSymbols(prev => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  // Filter out crowdfunding assets (managed via dedicated page)
  const filteredMetrics = useMemo(() => {
    if (!portfolioMetrics) return portfolioMetrics
    return {
      ...portfolioMetrics,
      assets: portfolioMetrics.assets.filter((a) => a.asset_type !== 'crowdfunding'),
    }
  }, [portfolioMetrics])

  // Group assets by platform for distribution view
  const platformDistribution = useMemo(() => {
    if (!filteredMetrics?.assets?.length) return []
    const map = new Map<string, {
      value: number
      totalInvested: number
      gainLoss: number
      totalFees: number
      assets: { symbol: string; value: number }[]
    }>()
    for (const asset of filteredMetrics.assets) {
      const platform = asset.exchange || 'Non assigné'
      const entry = map.get(platform) || { value: 0, totalInvested: 0, gainLoss: 0, totalFees: 0, assets: [] }
      entry.value += asset.current_value
      entry.totalInvested += asset.total_invested
      entry.gainLoss += asset.gain_loss
      entry.totalFees += asset.total_fees || 0
      entry.assets.push({ symbol: asset.symbol, value: asset.current_value })
      map.set(platform, entry)
    }
    return Array.from(map.entries())
      .map(([platform, data]) => ({
        platform,
        ...data,
        roi: data.totalInvested > 0
          ? ((data.value - data.totalInvested) / data.totalInvested) * 100
          : 0,
        netPnl: data.gainLoss - data.totalFees,
      }))
      .sort((a, b) => b.value - a.value)
  }, [filteredMetrics?.assets])

  // Group assets by symbol for aggregated view
  const groupedAssets = useMemo(() => {
    if (!filteredMetrics?.assets?.length) return []
    const filtered = filteredMetrics.assets.filter((asset) =>
      !platformFilter || (asset.exchange || 'Non assigné') === platformFilter
    )
    const map = new Map<string, GroupedAsset>()
    for (const asset of filtered) {
      const existing = map.get(asset.symbol)
      if (existing) {
        existing.assets.push(asset)
        existing.totalQuantity += asset.quantity
        existing.totalValue += asset.current_value
        existing.totalInvested += asset.total_invested
        existing.totalGainLoss += asset.gain_loss
        existing.isMultiPlatform = true
        // Weighted avg buy price
        const totalQty = existing.assets.reduce((s, a) => s + a.quantity, 0)
        existing.avgBuyPrice = totalQty > 0
          ? existing.totalInvested / totalQty
          : 0
        existing.totalGainLossPercent = existing.totalInvested > 0
          ? ((existing.totalValue - existing.totalInvested) / existing.totalInvested) * 100
          : 0
      } else {
        map.set(asset.symbol, {
          symbol: asset.symbol,
          name: asset.name,
          asset_type: asset.asset_type,
          assets: [asset],
          totalQuantity: asset.quantity,
          totalValue: asset.current_value,
          totalInvested: asset.total_invested,
          totalGainLoss: asset.gain_loss,
          totalGainLossPercent: asset.total_invested > 0
            ? ((asset.current_value - asset.total_invested) / asset.total_invested) * 100
            : 0,
          currentPrice: asset.current_price,
          avgBuyPrice: asset.avg_buy_price,
          isMultiPlatform: false,
        })
      }
    }
    // Use same current price across grouped assets
    for (const group of map.values()) {
      const priced = group.assets.find(a => a.current_price && a.current_price > 0)
      if (priced) group.currentPrice = priced.current_price
    }
    return Array.from(map.values()).sort((a, b) => b.totalValue - a.totalValue)
  }, [filteredMetrics?.assets, platformFilter])

  const hasPlatformData = platformDistribution.some((p) => p.platform !== 'Non assigné')

  // Detect if this is a crowdfunding portfolio (all assets are crowdfunding type)
  const isCrowdfundingPortfolio = useMemo(() => {
    if (!portfolioMetrics?.assets?.length) return false
    return portfolioMetrics.assets.every((a) => a.asset_type === 'crowdfunding')
  }, [portfolioMetrics?.assets])

  const statusBadge = (status?: string) => {
    switch (status) {
      case 'active':
        return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-gain/10 text-gain">En cours</span>
      case 'completed':
        return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">Remboursé</span>
      case 'delayed':
        return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-warning/10 text-warning">Retardé</span>
      case 'defaulted':
        return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-loss/10 text-loss">Défaut</span>
      default:
        return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{status || '-'}</span>
    }
  }

  const formatMaturityDate = (dateStr?: string) => {
    if (!dateStr) return '-'
    const d = new Date(dateStr)
    return d.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' })
  }

  const renderPlatformBadge = (asset: AssetMetrics) => {
    if (onUpdateAssetExchange) {
      return (
        <Popover open={platformPopover === asset.id} onOpenChange={(open) => setPlatformPopover(open ? asset.id : null)}>
          <PopoverTrigger asChild>
            <button className={`text-xs px-2 py-0.5 rounded inline-flex items-center gap-1 cursor-pointer hover:opacity-80 transition-opacity ${
              asset.exchange
                ? isColdWallet(asset.exchange)
                  ? 'bg-accent/10 text-accent'
                  : 'bg-muted text-muted-foreground'
                : 'bg-muted/50 text-muted-foreground'
            }`}>
              {asset.exchange && isColdWallet(asset.exchange) && <Shield className="h-3 w-3" />}
              {asset.exchange || 'Non assigné'}
              <ChevronDown className="h-3 w-3 opacity-50" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-44 p-1" align="center">
            <div className="max-h-52 overflow-y-auto">
              {ALL_PLATFORMS.map((platform) => (
                <button
                  key={platform}
                  className={`w-full text-left text-xs px-2 py-1.5 rounded flex items-center gap-2 hover:bg-muted transition-colors ${
                    asset.exchange === platform ? 'bg-muted font-medium' : ''
                  }`}
                  onClick={() => {
                    onUpdateAssetExchange(asset.id, platform)
                    setPlatformPopover(null)
                  }}
                >
                  {isColdWallet(platform) && <Shield className="h-3 w-3 text-accent shrink-0" />}
                  {!isColdWallet(platform) && <Building2 className="h-3 w-3 text-muted-foreground shrink-0" />}
                  {platform}
                </button>
              ))}
              {asset.exchange && (
                <button
                  className="w-full text-left text-xs px-2 py-1.5 rounded text-muted-foreground hover:bg-muted transition-colors"
                  onClick={() => {
                    onUpdateAssetExchange(asset.id, null)
                    setPlatformPopover(null)
                  }}
                >
                  Retirer la plateforme
                </button>
              )}
            </div>
          </PopoverContent>
        </Popover>
      )
    }
    if (asset.exchange) {
      return (
        <span className={`text-xs px-2 py-0.5 rounded inline-flex items-center gap-1 ${
          isColdWallet(asset.exchange)
            ? 'bg-accent/10 text-accent'
            : 'bg-muted text-muted-foreground'
        }`}>
          {isColdWallet(asset.exchange) && <Shield className="h-3 w-3" />}
          {asset.exchange}
        </span>
      )
    }
    return <span className="text-xs text-muted-foreground">-</span>
  }

  return (
    <>
      {/* Cash + Stablecoins cards side by side */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Cash disponible card */}
        {(() => {
          const manualCash = Object.values(cashBalances).reduce((sum, val) => sum + val, 0)
          const fiatCash = portfolioMetrics?.cash_from_fiat || 0
          const totalCash = manualCash + fiatCash
          const cashEntries = Object.entries(cashBalances)
          const fiatEntries = portfolioMetrics?.fiat_assets || []

          return (
            <Card
              elevation="interactive"
              className="cursor-pointer hover:bg-muted/50 transition-colors"
              onClick={onOpenCashBalance}
            >
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-gain/20 flex items-center justify-center shrink-0">
                    <Banknote className="h-5 w-5 text-gain" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm text-muted-foreground">Cash disponible</p>
                    <p className="text-xl font-bold">{formatCurrency(totalCash)}</p>
                    {(cashEntries.length > 0 || fiatEntries.length > 0) && (
                      <div className="text-xs text-muted-foreground mt-1">
                        {cashEntries.map(([ex, amt]) => (
                          <span key={ex} className="mr-2">{ex}: {formatCurrency(amt)}</span>
                        ))}
                        {fiatEntries.map((f) => (
                          <span key={f.id} className="mr-2">{f.symbol}: {formatCurrency(f.value)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })()}

        {/* Stablecoins card */}
        <Card elevation="raised">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
                <span className="text-accent font-bold text-sm">$</span>
              </div>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">Stablecoins</p>
                <p className="text-xl font-bold">
                  {formatCurrency(portfolioMetrics?.cash_from_stablecoins || 0)}
                </p>
                {(portfolioMetrics?.stablecoins?.filter(sc => sc.value >= 0.01)?.length ?? 0) > 0 && (
                  <div className="text-xs text-muted-foreground mt-1">
                    {portfolioMetrics!.stablecoins!.filter(sc => sc.value >= 0.01).map((sc) => (
                      <span key={sc.id} className="mr-2">{sc.symbol}: {sc.quantity.toFixed(2)}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Platform distribution */}
      {hasPlatformData && platformDistribution.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
          {platformDistribution.map(({ platform, value, assets, netPnl, roi }) => {
            const isWallet = isColdWallet(platform)
            const isUnassigned = platform === 'Non assigné'
            const isActive = platformFilter === platform
            return (
              <Card
                key={platform}
                elevation="interactive"
                className={`cursor-pointer transition-all ${
                  isActive
                    ? 'ring-2 ring-primary border-primary'
                    : platformFilter
                      ? 'opacity-50 hover:opacity-75'
                      : isWallet
                        ? 'border-accent/20 hover:border-accent/40'
                        : 'hover:bg-muted/50'
                }`}
                onClick={() => setPlatformFilter(isActive ? null : platform)}
              >
                <CardContent className="py-3 px-4">
                  <div className="flex items-center gap-2 mb-1.5">
                    {isWallet ? (
                      <Shield className="h-4 w-4 text-accent shrink-0" />
                    ) : isUnassigned ? null : (
                      <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                    <span className={`text-sm font-medium truncate ${isWallet ? 'text-accent' : ''}`}>
                      {platform}
                    </span>
                  </div>
                  <p className="text-lg font-bold">{formatCurrency(value)}</p>
                  <p className={`text-sm font-medium ${netPnl >= 0 ? 'text-gain' : 'text-loss'}`}>
                    {netPnl >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(Math.abs(netPnl))}
                  </p>
                  <p className={`text-xs ${roi >= 0 ? 'text-gain/80' : 'text-loss/80'}`}>
                    ROI: {roi >= 0 ? '+' : ''}{roi.toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {assets.length} actif{assets.length > 1 ? 's' : ''}
                  </p>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {loadingMetrics ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : portfolioMetrics && isCrowdfundingPortfolio && portfolioMetrics.assets.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Projet</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Plateforme</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Montant</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Taux</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Echéance</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Statut</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {portfolioMetrics.assets
                .filter((a) => !platformFilter || (a.exchange || 'Non assigné') === platformFilter)
                .map((asset) => (
                <tr key={asset.id} className="border-b last:border-0">
                  <td className="py-3 text-center">
                    <div className="flex flex-col items-center">
                      <AssetIconCompact symbol={asset.symbol} name={asset.name} assetType={asset.asset_type} size={32} />
                      <span className="text-xs text-muted-foreground mt-1 max-w-[120px] truncate">{asset.name || asset.symbol}</span>
                    </div>
                  </td>
                  <td className="text-center py-3">{renderPlatformBadge(asset)}</td>
                  <td className="text-center py-3 font-medium">{formatCurrency(asset.invested_amount || asset.total_invested)}</td>
                  <td className="text-center py-3">
                    {asset.interest_rate != null ? `${asset.interest_rate}%` : '-'}
                  </td>
                  <td className="text-center py-3 text-sm">{formatMaturityDate(asset.maturity_date)}</td>
                  <td className="text-center py-3">{statusBadge(asset.project_status)}</td>
                  <td className="text-center py-3">
                    <div className="flex justify-center gap-1">
                      <Button variant="ghost" size="icon" onClick={() => onDeleteAsset(asset)} title="Supprimer">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : portfolioMetrics && groupedAssets.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Actif</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Plateforme</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Quantité</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground" title="Prix de revient (frais inclus)">PRU</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Prix actuel</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Valeur</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">+/- Value</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground hidden lg:table-cell">Risque</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground hidden lg:table-cell w-[100px]">30j</th>
                <th scope="col" className="text-center py-2 text-sm font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {groupedAssets.map((group) => {
                const isExpanded = expandedSymbols.has(group.symbol)
                const isSingle = !group.isMultiPlatform

                return isSingle ? (
                  // Single platform — ligne cliquable vers la vue détail
                  <tr
                    key={group.assets[0].id}
                    className="border-b last:border-0 cursor-pointer hover:bg-muted/30 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                    {...detailRowProps(group)}
                  >
                    <td className="py-3 text-center">
                      <div className="flex justify-center">
                        <AssetIconCompact
                          symbol={group.symbol}
                          name={group.name}
                          assetType={group.asset_type}
                          size={36}
                        />
                      </div>
                    </td>
                    {/* stopPropagation : le popover plateforme ne doit pas ouvrir le détail */}
                    <td className="text-center py-3" onClick={(e) => e.stopPropagation()}>
                      {renderPlatformBadge(group.assets[0])}
                    </td>
                    <td className="text-center py-3">{group.totalQuantity.toFixed(group.totalQuantity < 1 ? 8 : 2)}</td>
                    <td className="text-center py-3 text-muted-foreground">
                      {group.assets[0].breakeven_price != null ? (
                        <span title={`PRA hors frais : ${group.avgBuyPrice > 0 ? formatCurrency(group.avgBuyPrice) : '-'}`}>
                          {formatCurrency(group.assets[0].breakeven_price)}
                        </span>
                      ) : group.avgBuyPrice > 0 ? formatCurrency(group.avgBuyPrice) : '-'}
                    </td>
                    <td className="text-center py-3">
                      {group.currentPrice ? formatCurrency(group.currentPrice) : '-'}
                    </td>
                    <td className="text-center py-3 font-medium">{formatCurrency(group.totalValue)}</td>
                    <td className={`text-center py-3 ${group.totalGainLoss >= 0 ? 'text-gain' : 'text-loss'}`}>
                      <div>
                        <p>{group.totalGainLoss >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(group.totalGainLoss)}</p>
                        <p className="text-xs">
                          {group.totalGainLoss >= 0 ? '\u25B2' : '\u25BC'}{' '}
                          {formatPercent(group.totalGainLossPercent)}
                        </p>
                        {group.assets[0].annualized_return != null && group.assets[0].holding_days != null && group.assets[0].holding_days >= 7 && (
                          <p className="text-[10px] text-muted-foreground mt-0.5" title={`Détenu depuis ${group.assets[0].holding_days}j`}>
                            CAGR: {group.assets[0].annualized_return >= 0 ? '+' : ''}{group.assets[0].annualized_return.toFixed(1)}%/an
                            {' '}({group.assets[0].holding_days < 365
                              ? `${group.assets[0].holding_days}j`
                              : `${(group.assets[0].holding_days / 365.25).toFixed(1)}a`
                            })
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="text-center py-3 hidden lg:table-cell">
                      {group.assets[0].risk_weight != null && group.assets[0].risk_weight > 0 ? (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          group.assets[0].risk_weight > 30 ? 'bg-loss/10 text-loss' :
                          group.assets[0].risk_weight > 15 ? 'bg-warning/10 text-warning' :
                          'bg-gain/10 text-gain'
                        }`}>
                          {group.assets[0].risk_weight.toFixed(1)}%
                        </span>
                      ) : '-'}
                    </td>
                    <td className="text-center py-3 hidden lg:table-cell">
                      {sparklines?.[group.symbol] ? (
                        <div className="flex justify-center">
                          <Sparkline
                            data={sparklines[group.symbol].prices}
                            positive={sparklines[group.symbol].change_pct >= 0}
                          />
                        </div>
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </td>
                    <td className="text-center py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-center gap-1">
                        <Button variant="ghost" size="icon" onClick={() => onAddTransaction(group.assets[0].id, group.symbol)} title="Ajouter une transaction">
                          <ArrowRightLeft className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => onDeleteAsset(group.assets[0])} title="Supprimer">
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  // Multi-platform — grouped row + expandable sub-rows
                  <Fragment key={group.symbol}>
                    <tr
                      className="border-b cursor-pointer hover:bg-muted/30 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                      {...detailRowProps(group)}
                    >
                      <td className="py-3 text-center">
                        <div className="flex justify-center items-center gap-1">
                          <AssetIconCompact
                            symbol={group.symbol}
                            name={group.name}
                            assetType={group.asset_type}
                            size={36}
                          />
                        </div>
                      </td>
                      <td className="text-center py-3">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                          aria-expanded={isExpanded}
                          aria-label={`${isExpanded ? 'Masquer' : 'Afficher'} les positions par plateforme de ${group.symbol}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleExpanded(group.symbol)
                          }}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          {isExpanded
                            ? <ChevronDown className="h-3.5 w-3.5" />
                            : <ChevronRight className="h-3.5 w-3.5" />
                          }
                          <span>{group.assets.length} plateformes</span>
                        </button>
                      </td>
                      <td className="text-center py-3 font-medium">{group.totalQuantity.toFixed(group.totalQuantity < 1 ? 8 : 2)}</td>
                      <td className="text-center py-3 text-muted-foreground">
                        {(() => {
                          const totalQty = group.assets.reduce((s, a) => s + a.quantity, 0)
                          if (totalQty <= 0) return '-'
                          // Même méthodologie que les lignes simples : breakeven backend (frais inclus, FIFO),
                          // pondéré par quantité — si toutes les positions l'exposent.
                          if (group.assets.every(a => a.breakeven_price != null)) {
                            const weightedBreakeven =
                              group.assets.reduce((s, a) => s + a.breakeven_price! * a.quantity, 0) / totalQty
                            return (
                              <span title={`PRA hors frais : ${group.avgBuyPrice > 0 ? formatCurrency(group.avgBuyPrice) : '-'}`}>
                                {formatCurrency(weightedBreakeven)}
                              </span>
                            )
                          }
                          // Fallback : recalcul front (invested + frais) / quantité.
                          const totalCost = group.assets.reduce((s, a) => s + a.total_invested + (a.total_fees || 0), 0)
                          return formatCurrency(totalCost / totalQty)
                        })()}
                      </td>
                      <td className="text-center py-3">
                        {group.currentPrice ? formatCurrency(group.currentPrice) : '-'}
                      </td>
                      <td className="text-center py-3 font-medium">{formatCurrency(group.totalValue)}</td>
                      <td className={`text-center py-3 ${group.totalGainLoss >= 0 ? 'text-gain' : 'text-loss'}`}>
                        <div>
                          <p>{group.totalGainLoss >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(group.totalGainLoss)}</p>
                          <p className="text-xs">
                            {group.totalGainLoss >= 0 ? '\u25B2' : '\u25BC'}{' '}
                            {formatPercent(group.totalGainLossPercent)}
                          </p>
                          {(() => {
                            // CAGR de groupe : moyenne pondérée par le capital investi,
                            // uniquement si les positions couvertes représentent >= 90 % du capital.
                            const withCagr = group.assets.filter(
                              a => a.annualized_return != null && a.holding_days != null && a.holding_days >= 7
                            )
                            if (withCagr.length === 0) return null
                            const coveredInvested = withCagr.reduce((s, a) => s + a.total_invested, 0)
                            const coverage = group.totalInvested > 0 ? coveredInvested / group.totalInvested : 0
                            if (coveredInvested <= 0 || coverage < 0.9) {
                              return (
                                <p
                                  className="text-[10px] text-muted-foreground mt-0.5"
                                  title="CAGR indisponible pour toutes les plateformes"
                                >
                                  CAGR: —
                                </p>
                              )
                            }
                            const weightedCagr =
                              withCagr.reduce((s, a) => s + a.annualized_return! * a.total_invested, 0) /
                              coveredInvested
                            return (
                              <p className="text-[10px] text-muted-foreground mt-0.5" title="Pondéré par le capital investi">
                                CAGR: {weightedCagr >= 0 ? '+' : ''}{weightedCagr.toFixed(1)}%/an
                              </p>
                            )
                          })()}
                        </div>
                      </td>
                      <td className="text-center py-3 hidden lg:table-cell">
                        {(() => {
                          const riskWt = group.assets[0]?.risk_weight || 0
                          if (riskWt <= 0) return '-'
                          return (
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              riskWt > 30 ? 'bg-loss/10 text-loss' :
                              riskWt > 15 ? 'bg-warning/10 text-warning' :
                              'bg-gain/10 text-gain'
                            }`}>
                              {riskWt.toFixed(1)}%
                            </span>
                          )
                        })()}
                      </td>
                      <td className="text-center py-3 hidden lg:table-cell">
                        {sparklines?.[group.symbol] ? (
                          <div className="flex justify-center">
                            <Sparkline
                              data={sparklines[group.symbol].prices}
                              positive={sparklines[group.symbol].change_pct >= 0}
                            />
                          </div>
                        ) : <span className="text-xs text-muted-foreground">-</span>}
                      </td>
                      <td className="text-center py-3" />
                    </tr>
                    {isExpanded && group.assets.map((asset) => (
                      <tr key={asset.id} className="border-b last:border-0 bg-muted/20">
                        <td className="py-2 text-center" />
                        <td className="text-center py-2">{renderPlatformBadge(asset)}</td>
                        <td className="text-center py-2 text-sm">{asset.quantity.toFixed(asset.quantity < 1 ? 8 : 2)}</td>
                        <td className="text-center py-2 text-sm text-muted-foreground">
                          {asset.breakeven_price != null ? (
                            <span title={`PRA hors frais : ${asset.avg_buy_price > 0 ? formatCurrency(asset.avg_buy_price) : '-'}`}>
                              {formatCurrency(asset.breakeven_price)}
                            </span>
                          ) : asset.avg_buy_price > 0 ? formatCurrency(asset.avg_buy_price) : '-'}
                        </td>
                        <td className="text-center py-2 text-sm">
                          {asset.current_price ? formatCurrency(asset.current_price) : '-'}
                        </td>
                        <td className="text-center py-2 text-sm">{formatCurrency(asset.current_value)}</td>
                        <td className={`text-center py-2 text-sm ${asset.gain_loss >= 0 ? 'text-gain' : 'text-loss'}`}>
                          {asset.gain_loss >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(asset.gain_loss)}
                        </td>
                        <td className="text-center py-2 hidden lg:table-cell">
                          {asset.risk_weight != null && asset.risk_weight > 0 ? (
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              asset.risk_weight > 30 ? 'bg-loss/10 text-loss' :
                              asset.risk_weight > 15 ? 'bg-warning/10 text-warning' :
                              'bg-gain/10 text-gain'
                            }`}>
                              {asset.risk_weight.toFixed(1)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td className="text-center py-2 hidden lg:table-cell">
                          {sparklines?.[group.symbol] ? (
                            <div className="flex justify-center">
                              <Sparkline
                                data={sparklines[group.symbol].prices}
                                positive={sparklines[group.symbol].change_pct >= 0}
                              />
                            </div>
                          ) : <span className="text-xs text-muted-foreground">-</span>}
                        </td>
                        <td className="text-center py-2">
                          <div className="flex justify-center gap-1">
                            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onAddTransaction(asset.id, asset.symbol)} title="Ajouter une transaction">
                              <ArrowRightLeft className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onDeleteAsset(asset)} title="Supprimer">
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="Aucun actif dans ce portefeuille" />
      )}
      <div className="mt-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onAddAsset(portfolioId, portfolioName)}
        >
          <Plus className="h-4 w-4 mr-1" />
          Ajouter un actif
        </Button>
      </div>

      <AssetDetailSheet
        open={detailOpen}
        onOpenChange={setDetailOpen}
        group={detailGroup}
        portfolioTotalValue={portfolioMetrics?.total_value}
        sparkline={detailGroup ? sparklines?.[detailGroup.symbol] : undefined}
      />
    </>
  )
}
