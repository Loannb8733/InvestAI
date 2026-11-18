import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Coins, PieChart, Target, TrendingDown, TrendingUp, Wallet, X } from 'lucide-react'
import StatCard from '@/components/ui/stat-card'
import { Badge } from '@/components/ui/badge'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { Sparkline } from '@/components/ui/sparkline'
import { formatPercent } from '@/lib/utils'
import { formatDetailQuantity, formatSignedPercent } from '../format'
import { weightedBreakeven } from '../grouping'
import { useMoney } from '../hooks'
import type { Position, PositionGroup, SparklineSeries } from '../types'
import AssetTransactions from './AssetTransactions'

interface AssetDetailSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  group: PositionGroup | null
  portfolioTotalValue: number | undefined
  sparkline: SparklineSeries | undefined
}

const assetTypeLabels: Record<string, string> = {
  crypto: 'Crypto',
  stock: 'Action',
  etf: 'ETF',
  real_estate: 'Immobilier',
  bond: 'Obligation',
  fiat: 'Fiat',
  other: 'Autre',
}

function SparklineTrend({ sparkline }: { sparkline: SparklineSeries }) {
  const positive = sparkline.change_pct >= 0
  return (
    <div className="mt-1 flex items-center justify-end gap-2">
      <Sparkline data={sparkline.prices} positive={positive} />
      <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${positive ? 'text-gain' : 'text-loss'}`}>
        {positive ? <TrendingUp aria-hidden className="h-3 w-3" /> : <TrendingDown aria-hidden className="h-3 w-3" />}
        {`${formatSignedPercent(sparkline.change_pct, 2)} · 30j`}
      </span>
    </div>
  )
}

function PlatformPositions({ assets }: { assets: Position[] }) {
  const money = useMoney()
  return (
    <section aria-label="Positions par plateforme">
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">Positions par plateforme</h3>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40">
              <th scope="col" className="px-3 py-2 text-left font-medium text-muted-foreground">Plateforme</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">Quantité</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">Valeur</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">PRU</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => (
              <tr key={asset.id} className="border-b last:border-0">
                <td className="px-3 py-2">{asset.exchange || 'Non assigné'}</td>
                <td className="px-3 py-2 text-right">{formatDetailQuantity(asset.quantity)}</td>
                <td className="px-3 py-2 text-right font-medium">{money(asset.current_value)}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">{money(asset.breakeven_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function DetailKpis({ group, portfolioTotalValue }: { group: PositionGroup; portfolioTotalValue: number | undefined }) {
  const money = useMoney()
  const portfolioShare =
    portfolioTotalValue && portfolioTotalValue > 0 ? (group.totalValue / portfolioTotalValue) * 100 : null
  return (
    <div className="grid grid-cols-2 gap-3">
      <StatCard static label="Quantité totale" icon={Coins} value={group.totalQuantity} format={formatDetailQuantity} />
      <StatCard static label="Valeur actuelle" icon={Wallet} value={group.totalValue} format={money} />
      <StatCard
        static
        label="PRU"
        tooltip="Prix de revient unitaire, frais inclus."
        icon={Target}
        value={weightedBreakeven(group.assets)}
        format={money}
        hint={group.avgBuyPrice > 0 ? `PRA hors frais : ${money(group.avgBuyPrice)}` : undefined}
      />
      <StatCard
        static
        label="P&L latent"
        icon={TrendingUp}
        value={group.totalGainLoss}
        format={money}
        delta={group.totalGainLossPercent}
        tone="auto"
      />
      <StatCard
        static
        label="Part du portefeuille"
        icon={PieChart}
        value={portfolioShare}
        format={formatPercent}
        hint={`Investi : ${money(group.totalInvested)}`}
      />
    </div>
  )
}

export default function AssetDetailSheet({ open, onOpenChange, group, portfolioTotalValue, sparkline }: AssetDetailSheetProps) {
  const money = useMoney()
  if (!group) return null
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col gap-5 overflow-y-auto border-l bg-background p-6 shadow-md transition ease-in-out data-[state=closed]:duration-300 data-[state=open]:duration-500 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-xl"
          aria-label={`Détail de l'actif ${group.symbol}`}
        >
          <div className="flex items-start justify-between gap-4 pr-8">
            <div className="flex items-center gap-3">
              <AssetIconCompact symbol={group.symbol} name={group.name ?? undefined} assetType={group.asset_type} size={44} />
              <div className="min-w-0">
                <DialogPrimitive.Title className="text-xl font-semibold leading-tight tracking-tight">
                  {group.symbol}
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="truncate text-sm text-muted-foreground">
                  {group.name || group.symbol}
                </DialogPrimitive.Description>
                <Badge variant="secondary" className="mt-1">
                  {assetTypeLabels[group.asset_type] || group.asset_type}
                </Badge>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-lg font-semibold">{group.currentPrice ? money(group.currentPrice) : '—'}</p>
              {sparkline && sparkline.prices.length > 1 && <SparklineTrend sparkline={sparkline} />}
            </div>
          </div>

          <DetailKpis group={group} portfolioTotalValue={portfolioTotalValue} />

          {group.assets.length > 1 && <PlatformPositions assets={group.assets} />}

          <AssetTransactions assets={group.assets} open={open} />

          <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2">
            <X className="h-4 w-4" />
            <span className="sr-only">Fermer</span>
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
