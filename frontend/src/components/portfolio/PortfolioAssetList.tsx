import { Button } from '@/components/ui/button'
import { formatCurrency, formatPercent } from '@/lib/utils'
import {
  Plus,
  Loader2,
  Trash2,
  ArrowRightLeft,
  Banknote,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { AssetIconCompact } from '@/components/ui/asset-icon'

interface AssetMetrics {
  id: string
  symbol: string
  name?: string
  asset_type: string
  quantity: number
  avg_buy_price: number
  current_price?: number
  current_value: number
  total_invested: number
  gain_loss: number
  gain_loss_percent: number
}

interface StablecoinEntry {
  id: string
  symbol: string
  quantity: number
  value: number
}

interface PortfolioMetrics {
  total_value: number
  total_invested: number
  total_gain_loss: number
  total_gain_loss_percent: number
  assets: AssetMetrics[]
  cash_from_stablecoins?: number
  stablecoins?: StablecoinEntry[]
  cash_from_fiat?: number
  fiat_assets?: StablecoinEntry[]
}

interface PortfolioAssetListProps {
  portfolioMetrics: PortfolioMetrics | undefined
  loadingMetrics: boolean
  cashBalances: Record<string, number>
  portfolioId: string
  portfolioName: string
  onAddAsset: (portfolioId: string, portfolioName: string) => void
  onAddTransaction: (assetId: string, assetSymbol: string) => void
  onDeleteAsset: (asset: AssetMetrics) => void
  onOpenCashBalance: () => void
}

export default function PortfolioAssetList({
  portfolioMetrics,
  loadingMetrics,
  cashBalances,
  portfolioId,
  portfolioName,
  onAddAsset,
  onAddTransaction,
  onDeleteAsset,
  onOpenCashBalance,
}: PortfolioAssetListProps) {
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
              className="cursor-pointer hover:bg-muted/50 transition-colors"
              onClick={onOpenCashBalance}
            >
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                    <Banknote className="h-5 w-5 text-emerald-500" />
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
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                <span className="text-blue-500 font-bold text-sm">$</span>
              </div>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">Stablecoins</p>
                <p className="text-xl font-bold">
                  {formatCurrency(portfolioMetrics?.cash_from_stablecoins || 0)}
                </p>
                {(portfolioMetrics?.stablecoins?.length ?? 0) > 0 && (
                  <div className="text-xs text-muted-foreground mt-1">
                    {portfolioMetrics!.stablecoins!.map((sc) => (
                      <span key={sc.id} className="mr-2">{sc.symbol}: {sc.quantity.toFixed(2)}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {loadingMetrics ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : portfolioMetrics && portfolioMetrics.assets.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actif</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Quantité</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">PRA</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Prix actuel</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Valeur</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">+/- Value</th>
                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {portfolioMetrics.assets.map((asset) => (
                <tr key={asset.id} className="border-b last:border-0">
                  <td className="py-3 text-center">
                    <div className="flex justify-center">
                      <AssetIconCompact
                        symbol={asset.symbol}
                        name={asset.name}
                        assetType={asset.asset_type}
                        size={36}
                      />
                    </div>
                  </td>
                  <td className="text-center py-3">{asset.quantity.toFixed(asset.quantity < 1 ? 8 : 2)}</td>
                  <td className="text-center py-3 text-muted-foreground">
                    {asset.avg_buy_price > 0 ? formatCurrency(asset.avg_buy_price) : '-'}
                  </td>
                  <td className="text-center py-3">
                    {asset.current_price ? formatCurrency(asset.current_price) : '-'}
                  </td>
                  <td className="text-center py-3 font-medium">{formatCurrency(asset.current_value)}</td>
                  <td className={`text-center py-3 ${asset.gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    <div>
                      <p>{asset.gain_loss >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(asset.gain_loss)}</p>
                      <p className="text-xs">
                        {asset.gain_loss >= 0 ? '\u25B2' : '\u25BC'}{' '}
                        {asset.avg_buy_price > 0 && asset.current_price
                          ? `${((asset.current_price - asset.avg_buy_price) / asset.avg_buy_price * 100).toFixed(2)}%`
                          : formatPercent(asset.gain_loss_percent)}
                      </p>
                    </div>
                  </td>
                  <td className="text-center py-3">
                    <div className="flex justify-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => onAddTransaction(asset.id, asset.symbol)}
                        title="Ajouter une transaction"
                      >
                        <ArrowRightLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => onDeleteAsset(asset)}
                        title="Supprimer"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 text-muted-foreground">
          Aucun actif dans ce portefeuille
        </div>
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
    </>
  )
}
