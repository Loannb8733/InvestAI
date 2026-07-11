import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useQueries } from '@tanstack/react-query'
import { Coins, PieChart, Target, TrendingDown, TrendingUp, Wallet, X } from 'lucide-react'
import StatCard from '@/components/ui/stat-card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/empty-state'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { Sparkline } from '@/components/ui/sparkline'
import { transactionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { formatCurrency, formatPercent } from '@/lib/utils'
import type { AssetMetrics } from '@/types'

/**
 * AssetDetailSheet — panneau latéral de détail d'un actif du portefeuille.
 *
 * Ouvert au clic sur une ligne de PortfolioAssetList (position simple ou
 * groupe multi-plateformes). Construit sur les primitives Radix Dialog
 * (pas de ui/sheet.tsx dans le design system) : focus trap, Escape et
 * aria-modal sont gérés nativement.
 *
 * Lazy : les transactions ne sont fetchées qu'à l'ouverture (`enabled`).
 */

/** Structure compatible avec le GroupedAsset de PortfolioAssetList. */
export interface AssetDetailGroup {
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

interface AssetDetailSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  group: AssetDetailGroup | null
  /** Valeur totale du portefeuille — pour le KPI « % du portefeuille ». */
  portfolioTotalValue?: number
  /** Sparkline 30j déjà chargée par la liste (pas de refetch). */
  sparkline?: { prices: number[]; change_pct: number }
}

/** Shape snake_case renvoyée par GET /transactions. */
interface AssetTransaction {
  id: string
  transaction_type: string
  quantity: number
  price: number
  fee: number | null
  currency: string
  executed_at: string | null
  created_at: string
  exchange: string | null
}

const TX_LIMIT = 20

const assetTypeLabels: Record<string, string> = {
  crypto: 'Crypto',
  stock: 'Action',
  etf: 'ETF',
  real_estate: 'Immobilier',
  bond: 'Obligation',
  crowdfunding: 'Crowdfunding',
  fiat: 'Fiat',
  other: 'Autre',
}

const txTypeLabels: Record<string, string> = {
  buy: 'Achat',
  sell: 'Vente',
  transfer_in: 'Transfert entrant',
  transfer_out: 'Transfert sortant',
  staking_reward: 'Reward',
  airdrop: 'Airdrop',
  conversion_in: 'Conversion entrante',
  conversion_out: 'Conversion sortante',
  dividend: 'Dividende',
  interest: 'Intérêts',
  fee: 'Frais',
  staking: 'Staking',
  unstaking: 'Unstaking',
}

const txBadgeVariant = (type: string): 'gain' | 'loss' | 'warning' | 'secondary' => {
  switch (type) {
    case 'buy':
    case 'conversion_in':
    case 'dividend':
      return 'gain'
    case 'sell':
    case 'fee':
      return 'loss'
    case 'transfer_out':
    case 'conversion_out':
      return 'warning'
    default:
      return 'secondary'
  }
}

const formatQty = (q: number) =>
  q.toLocaleString('fr-FR', { maximumFractionDigits: Math.abs(q) < 1 ? 8 : 4 })

const formatTxDate = (tx: AssetTransaction) =>
  new Date(tx.executed_at || tx.created_at).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })

export default function AssetDetailSheet({
  open,
  onOpenChange,
  group,
  portfolioTotalValue,
  sparkline,
}: AssetDetailSheetProps) {
  const assets = group?.assets ?? []

  // Une requête par position (lazy : uniquement panneau ouvert). Pour un
  // groupe multi-plateformes, on agrège les transactions de toutes les
  // positions puis on garde les 20 plus récentes.
  const txQueries = useQueries({
    queries: assets.map((asset) => ({
      queryKey: queryKeys.transactions.byAsset(asset.id),
      queryFn: async () =>
        (await transactionsApi.list({ asset_id: asset.id, limit: TX_LIMIT })) as AssetTransaction[],
      enabled: open && assets.length > 0,
      staleTime: 30_000,
    })),
  })

  if (!group) return null

  const txLoading = txQueries.some((q) => q.isLoading)
  const txError = txQueries.length > 0 && txQueries.every((q) => q.isError)
  const transactions = txQueries
    .flatMap((q) => q.data ?? [])
    .sort(
      (a, b) =>
        new Date(b.executed_at || b.created_at).getTime() -
        new Date(a.executed_at || a.created_at).getTime()
    )
    .slice(0, TX_LIMIT)

  // PRU (frais inclus) — même méthodologie que la liste : breakeven backend
  // pondéré par quantité si disponible partout, sinon recalcul front.
  const totalQty = assets.reduce((s, a) => s + a.quantity, 0)
  let breakeven: number | null = null
  if (totalQty > 0) {
    if (assets.every((a) => a.breakeven_price != null)) {
      breakeven = assets.reduce((s, a) => s + a.breakeven_price! * a.quantity, 0) / totalQty
    } else {
      breakeven =
        assets.reduce((s, a) => s + a.total_invested + (a.total_fees || 0), 0) / totalQty
    }
  }

  const portfolioShare =
    portfolioTotalValue && portfolioTotalValue > 0
      ? (group.totalValue / portfolioTotalValue) * 100
      : null

  const sparkPositive = (sparkline?.change_pct ?? 0) >= 0

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col gap-5 overflow-y-auto border-l bg-background p-6 shadow-md transition ease-in-out data-[state=closed]:duration-300 data-[state=open]:duration-500 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-xl"
          aria-label={`Détail de l'actif ${group.symbol}`}
        >
          {/* En-tête */}
          <div className="flex items-start justify-between gap-4 pr-8">
            <div className="flex items-center gap-3">
              <AssetIconCompact
                symbol={group.symbol}
                name={group.name}
                assetType={group.asset_type}
                size={44}
              />
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
              <p className="text-lg font-semibold">
                {group.currentPrice ? formatCurrency(group.currentPrice) : '—'}
              </p>
              {sparkline && sparkline.prices.length > 1 && (
                <div className="mt-1 flex items-center justify-end gap-2">
                  <Sparkline data={sparkline.prices} positive={sparkPositive} />
                  <span
                    className={`inline-flex items-center gap-0.5 text-xs font-medium ${
                      sparkPositive ? 'text-gain' : 'text-loss'
                    }`}
                  >
                    {sparkPositive ? (
                      <TrendingUp aria-hidden className="h-3 w-3" />
                    ) : (
                      <TrendingDown aria-hidden className="h-3 w-3" />
                    )}
                    {sparkPositive ? '+' : ''}
                    {sparkline.change_pct.toFixed(2)} % · 30j
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              static
              label="Quantité totale"
              icon={Coins}
              value={group.totalQuantity}
              format={formatQty}
            />
            <StatCard
              static
              label="Valeur actuelle"
              icon={Wallet}
              value={group.totalValue}
              format={formatCurrency}
            />
            <StatCard
              static
              label="PRU"
              tooltip="Prix de revient unitaire, frais inclus."
              icon={Target}
              value={breakeven}
              format={formatCurrency}
              hint={
                group.avgBuyPrice > 0
                  ? `PRA hors frais : ${formatCurrency(group.avgBuyPrice)}`
                  : undefined
              }
            />
            <StatCard
              static
              label="P&L latent"
              icon={TrendingUp}
              value={group.totalGainLoss}
              format={formatCurrency}
              delta={group.totalGainLossPercent}
              tone="auto"
            />
            <StatCard
              static
              label="Part du portefeuille"
              icon={PieChart}
              value={portfolioShare}
              format={formatPercent}
              hint={`Investi : ${formatCurrency(group.totalInvested)}`}
            />
          </div>

          {/* Positions par plateforme */}
          {group.assets.length > 1 && (
            <section aria-label="Positions par plateforme">
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">
                Positions par plateforme
              </h3>
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/40">
                      <th scope="col" className="px-3 py-2 text-left font-medium text-muted-foreground">
                        Plateforme
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Quantité
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Valeur
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        PRU
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.assets.map((asset) => (
                      <tr key={asset.id} className="border-b last:border-0">
                        <td className="px-3 py-2">{asset.exchange || 'Non assigné'}</td>
                        <td className="px-3 py-2 text-right">{formatQty(asset.quantity)}</td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatCurrency(asset.current_value)}
                        </td>
                        <td className="px-3 py-2 text-right text-muted-foreground">
                          {asset.breakeven_price != null
                            ? formatCurrency(asset.breakeven_price)
                            : asset.avg_buy_price > 0
                              ? formatCurrency(asset.avg_buy_price)
                              : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Transactions */}
          <section aria-label="Transactions de l'actif">
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-medium text-muted-foreground">Transactions</h3>
              {!txLoading && transactions.length >= TX_LIMIT && (
                <span className="text-xs text-muted-foreground">
                  {TX_LIMIT} plus récentes
                </span>
              )}
            </div>
            {txLoading ? (
              <div className="space-y-2" aria-hidden>
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            ) : txError ? (
              <EmptyState
                variant="error"
                title="Impossible de charger les transactions"
                description="Réessayez en rouvrant le panneau."
              />
            ) : transactions.length === 0 ? (
              <EmptyState
                title="Aucune transaction"
                description="Cet actif n'a pas encore de transaction enregistrée."
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/40">
                      <th scope="col" className="px-3 py-2 text-left font-medium text-muted-foreground">
                        Date
                      </th>
                      <th scope="col" className="px-3 py-2 text-left font-medium text-muted-foreground">
                        Type
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Quantité
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Prix
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((tx) => (
                      <tr key={tx.id} className="border-b last:border-0">
                        <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
                          {formatTxDate(tx)}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant={txBadgeVariant(tx.transaction_type)}>
                            {txTypeLabels[tx.transaction_type] || tx.transaction_type}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right">{formatQty(tx.quantity)}</td>
                        <td className="px-3 py-2 text-right text-muted-foreground">
                          {formatCurrency(tx.price)}
                        </td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatCurrency(tx.quantity * tx.price)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
            <X className="h-4 w-4" />
            <span className="sr-only">Fermer</span>
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
