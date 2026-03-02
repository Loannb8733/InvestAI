import { Fragment, useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { portfoliosApi, assetsApi, dashboardApi, transactionsApi } from '@/services/api'
import AddPortfolioForm from '@/components/forms/AddPortfolioForm'
import AddAssetForm from '@/components/forms/AddAssetForm'
import AddTransactionForm from '@/components/forms/AddTransactionForm'
import ImportCSVForm from '@/components/forms/ImportCSVForm'
import CashBalanceForm from '@/components/forms/CashBalanceForm'
import { useToast } from '@/hooks/use-toast'
import {
  Plus,
  Wallet,
  Loader2,
  Trash2,
  Upload,
  Download,
  History,
  TrendingUp,
  PiggyBank,
  AlertTriangle,
  Shield,
  Building2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { AssetIconCompact } from '@/components/ui/asset-icon'
import { isColdWallet } from '@/lib/platforms'
import PortfolioAssetList from '@/components/portfolio/PortfolioAssetList'
import CreatePortfolioForm from '@/components/portfolio/CreatePortfolioForm'

interface Portfolio {
  id: string
  name: string
  description?: string
  cash_balances?: Record<string, number>
}

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

interface HistoricalAsset {
  id: string
  symbol: string
  name?: string
  asset_type: string
  exchange?: string | null
  current_quantity: number
  total_bought: number
  total_bought_value: number
  total_sold: number
  total_sold_value: number
  total_fees: number
  realized_gain: number
  first_transaction?: string
  last_transaction?: string
}

interface PortfolioHistory {
  total_invested_all_time: number
  total_sold: number
  total_fees: number
  realized_gains: number
  current_holdings_count: number
  sold_assets_count: number
  sold_assets: HistoricalAsset[]
}

export default function PortfolioPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [showAddPortfolio, setShowAddPortfolio] = useState(false)
  const [showAddAsset, setShowAddAsset] = useState<{ portfolioId: string; portfolioName: string } | null>(null)
  const [showAddTransaction, setShowAddTransaction] = useState<{ assetId: string; assetSymbol: string } | null>(null)
  const [showImportCSV, setShowImportCSV] = useState(false)
  const [showCashBalance, setShowCashBalance] = useState(false)
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('current')
  const [deleteAsset, setDeleteAsset] = useState<AssetMetrics | null>(null)
  const [deletePortfolio, setDeletePortfolio] = useState<Portfolio | null>(null)
  const [historyPlatformFilter, setHistoryPlatformFilter] = useState<string | null>(null)
  const [historyExpandedSymbols, setHistoryExpandedSymbols] = useState<Set<string>>(new Set())

  const toggleHistoryExpanded = (symbol: string) => {
    setHistoryExpandedSymbols(prev => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  // Fetch portfolios
  const { data: portfolios, isLoading: loadingPortfolios } = useQuery<Portfolio[]>({
    queryKey: queryKeys.portfolios.list(),
    queryFn: portfoliosApi.list,
    staleTime: 60_000,
  })

  // Fetch portfolio metrics (current holdings)
  const { data: portfolioMetrics, isLoading: loadingMetrics } = useQuery<PortfolioMetrics>({
    queryKey: queryKeys.portfolios.metrics(selectedPortfolio),
    queryFn: () => dashboardApi.getPortfolioMetrics(selectedPortfolio!),
    enabled: !!selectedPortfolio,
    placeholderData: keepPreviousData,
  })

  // Fetch portfolio history (including sold assets)
  const { data: portfolioHistory, isLoading: loadingHistory, isPlaceholderData: isHistoryStale } = useQuery<PortfolioHistory>({
    queryKey: queryKeys.portfolios.history(selectedPortfolio),
    queryFn: () => dashboardApi.getPortfolioHistory(selectedPortfolio!),
    enabled: !!selectedPortfolio && activeTab === 'history',
    placeholderData: keepPreviousData,
  })

  // Delete asset mutation
  const deleteAssetMutation = useMutation({
    mutationFn: assetsApi.delete,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      setDeleteAsset(null)
      toast({ title: 'Actif et transactions supprimés' })
    },
    onError: () => {
      setDeleteAsset(null)
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer l\'actif' })
    },
  })

  // Update asset exchange mutation
  const updateAssetExchangeMutation = useMutation({
    mutationFn: ({ id, exchange }: { id: string; exchange: string | null }) =>
      assetsApi.update(id, { exchange }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Plateforme mise à jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de modifier la plateforme' })
    },
  })

  // Delete portfolio mutation
  const deletePortfolioMutation = useMutation({
    mutationFn: portfoliosApi.delete,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      setSelectedPortfolio(null)
      setDeletePortfolio(null)
      toast({ title: 'Portefeuille supprimé' })
    },
    onError: () => {
      setDeletePortfolio(null)
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le portefeuille' })
    },
  })

  // Auto-select first portfolio
  useEffect(() => {
    if (portfolios && portfolios.length > 0 && !selectedPortfolio) {
      setSelectedPortfolio(portfolios[0].id)
    }
  }, [portfolios, selectedPortfolio])

  if (loadingPortfolios) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Empty state
  if (!portfolios || portfolios.length === 0) {
    return (
      <CreatePortfolioForm
        showAddPortfolio={showAddPortfolio}
        onShowAddPortfolioChange={setShowAddPortfolio}
      />
    )
  }

  const currentPortfolio = portfolios.find((p) => p.id === selectedPortfolio)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Portefeuille</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowImportCSV(true)}>
            <Upload className="h-4 w-4 mr-2" />
            Importer CSV
          </Button>
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const blob = await transactionsApi.exportCSV(selectedPortfolio || undefined)
                const url = window.URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = 'transactions_export.csv'
                a.click()
                window.URL.revokeObjectURL(url)
                toast({ title: 'Export réussi', description: 'Le fichier CSV a été téléchargé.' })
              } catch {
                toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible d\'exporter les transactions.' })
              }
            }}
          >
            <Download className="h-4 w-4 mr-2" />
            Exporter CSV
          </Button>
          <Button onClick={() => setShowAddPortfolio(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nouveau portefeuille
          </Button>
        </div>
      </div>

      {/* Portfolio selector */}
      <div className="flex gap-2 flex-wrap">
        {portfolios.map((portfolio) => (
          <Button
            key={portfolio.id}
            variant={selectedPortfolio === portfolio.id ? 'default' : 'outline'}
            onClick={() => {
              setSelectedPortfolio(portfolio.id)
              setHistoryPlatformFilter(null)
              setHistoryExpandedSymbols(new Set())
            }}
          >
            {portfolio.name}
          </Button>
        ))}
      </div>

      {/* Selected portfolio */}
      {currentPortfolio && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                  <Wallet className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>{currentPortfolio.name}</CardTitle>
                  {currentPortfolio.description && (
                    <p className="text-sm text-muted-foreground">{currentPortfolio.description}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4">
                {portfolioMetrics && (
                  <div className="text-right">
                    <p className="text-2xl font-bold">
                      {formatCurrency(
                        portfolioMetrics.total_value
                        + (portfolioMetrics.cash_from_stablecoins || 0)
                        + (portfolioMetrics.cash_from_fiat || 0)
                      )}
                    </p>
                    <p className={`text-sm ${portfolioMetrics.total_gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {portfolioMetrics.total_gain_loss >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(portfolioMetrics.total_gain_loss)} ({formatPercent(portfolioMetrics.total_gain_loss_percent)})
                    </p>
                  </div>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDeletePortfolio(currentPortfolio)}
                  title="Supprimer le portefeuille"
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="current" className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  Actifs actuels
                </TabsTrigger>
                <TabsTrigger value="history" className="flex items-center gap-2">
                  <History className="h-4 w-4" />
                  Historique
                </TabsTrigger>
              </TabsList>

              {/* Current Holdings Tab */}
              <TabsContent value="current">
                <PortfolioAssetList
                  portfolioMetrics={portfolioMetrics}
                  loadingMetrics={loadingMetrics}
                  cashBalances={currentPortfolio.cash_balances || {}}
                  portfolioId={currentPortfolio.id}
                  portfolioName={currentPortfolio.name}
                  onAddAsset={(pId, pName) => setShowAddAsset({ portfolioId: pId, portfolioName: pName })}
                  onAddTransaction={(aId, aSym) => setShowAddTransaction({ assetId: aId, assetSymbol: aSym })}
                  onDeleteAsset={(asset) => setDeleteAsset(asset)}
                  onOpenCashBalance={() => setShowCashBalance(true)}
                  onUpdateAssetExchange={(id, exchange) => updateAssetExchangeMutation.mutate({ id, exchange })}
                />
              </TabsContent>

              {/* History Tab */}
              <TabsContent value="history">
                {loadingHistory ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  </div>
                ) : portfolioHistory ? (
                  <div className={`space-y-6 ${isHistoryStale ? 'opacity-50 pointer-events-none' : ''}`}>
                    {isHistoryStale && (
                      <div className="flex items-center justify-center py-2">
                        <Loader2 className="h-4 w-4 animate-spin text-primary mr-2" />
                        <span className="text-sm text-muted-foreground">Chargement...</span>
                      </div>
                    )}
                    {/* Summary cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-blue-500/20 flex items-center justify-center">
                              <PiggyBank className="h-5 w-5 text-blue-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Total investi (historique)</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_invested_all_time)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-green-500/20 flex items-center justify-center">
                              <TrendingUp className="h-5 w-5 text-green-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Total vendu</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_sold)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="pt-6">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-orange-500/20 flex items-center justify-center">
                              <History className="h-5 w-5 text-orange-500" />
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">Frais totaux</p>
                              <p className="text-xl font-bold">{formatCurrency(portfolioHistory.total_fees)}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>

                    {/* Sold assets table */}
                    {portfolioHistory.sold_assets.length > 0 ? (
                      <div>
                        <h3 className="text-lg font-semibold mb-3">
                          Actifs vendus ({(() => {
                            const filtered = historyPlatformFilter
                              ? portfolioHistory.sold_assets.filter(a => (a.exchange || 'Non assigné') === historyPlatformFilter)
                              : portfolioHistory.sold_assets
                            return new Set(filtered.map(a => a.symbol)).size
                          })()})
                        </h3>
                        {/* Platform filter cards */}
                        {(() => {
                          const platforms = new Map<string, { value: number; count: number }>()
                          portfolioHistory.sold_assets.forEach((a) => {
                            const p = a.exchange || 'Non assigné'
                            const entry = platforms.get(p) || { value: 0, count: 0 }
                            entry.value += a.total_sold_value
                            entry.count += 1
                            platforms.set(p, entry)
                          })
                          if (platforms.size === 0) return null
                          return (
                            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
                              {Array.from(platforms.entries())
                                .sort((a, b) => b[1].value - a[1].value)
                                .map(([platform, data]) => {
                                  const isWallet = isColdWallet(platform)
                                  const isUnassigned = platform === 'Non assigné'
                                  const isActive = historyPlatformFilter === platform
                                  return (
                                    <Card
                                      key={platform}
                                      className={`cursor-pointer transition-all ${
                                        isActive
                                          ? 'ring-2 ring-primary border-primary'
                                          : historyPlatformFilter
                                            ? 'opacity-50 hover:opacity-75'
                                            : isWallet
                                              ? 'border-blue-500/20 hover:border-blue-500/40'
                                              : 'hover:bg-muted/50'
                                      }`}
                                      onClick={() => setHistoryPlatformFilter(isActive ? null : platform)}
                                    >
                                      <CardContent className="py-3 px-4">
                                        <div className="flex items-center gap-2 mb-1.5">
                                          {isWallet ? (
                                            <Shield className="h-4 w-4 text-blue-500 shrink-0" />
                                          ) : isUnassigned ? null : (
                                            <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                                          )}
                                          <span className={`text-sm font-medium truncate ${isWallet ? 'text-blue-500' : ''}`}>
                                            {platform}
                                          </span>
                                        </div>
                                        <p className="text-lg font-bold">{formatCurrency(data.value)}</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                          {data.count} actif{data.count > 1 ? 's' : ''}
                                        </p>
                                      </CardContent>
                                    </Card>
                                  )
                                })}
                            </div>
                          )
                        })()}
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b">
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Actif</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Plateforme</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Qté achetée</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Total investi</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Qté vendue</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">Total vendu</th>
                                <th className="text-center py-2 text-sm font-medium text-muted-foreground">+/- Réalisé</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(() => {
                                const filtered = portfolioHistory.sold_assets
                                  .filter((asset) => !historyPlatformFilter || (asset.exchange || 'Non assigné') === historyPlatformFilter)
                                // Group by symbol
                                const groups = new Map<string, { symbol: string; name: string | undefined; asset_type: string; assets: typeof filtered; totalBought: number; totalBoughtValue: number; totalSold: number; totalSoldValue: number; realizedGain: number }>()
                                for (const asset of filtered) {
                                  const existing = groups.get(asset.symbol)
                                  if (existing) {
                                    existing.assets.push(asset)
                                    existing.totalBought += asset.total_bought
                                    existing.totalBoughtValue += asset.total_bought_value
                                    existing.totalSold += asset.total_sold
                                    existing.totalSoldValue += asset.total_sold_value
                                    existing.realizedGain += asset.realized_gain
                                  } else {
                                    groups.set(asset.symbol, {
                                      symbol: asset.symbol,
                                      name: asset.name,
                                      asset_type: asset.asset_type,
                                      assets: [asset],
                                      totalBought: asset.total_bought,
                                      totalBoughtValue: asset.total_bought_value,
                                      totalSold: asset.total_sold,
                                      totalSoldValue: asset.total_sold_value,
                                      realizedGain: asset.realized_gain,
                                    })
                                  }
                                }
                                return Array.from(groups.values())
                                  .sort((a, b) => b.totalBoughtValue - a.totalBoughtValue)
                                  .map((group) => {
                                    const isMulti = group.assets.length > 1
                                    const isExpanded = historyExpandedSymbols.has(group.symbol)

                                    if (!isMulti) {
                                      const asset = group.assets[0]
                                      return (
                                        <tr key={asset.id} className="border-b last:border-0">
                                          <td className="py-3 text-center">
                                            <div className="flex justify-center">
                                              <AssetIconCompact symbol={asset.symbol} name={asset.name} assetType={asset.asset_type} size={36} />
                                            </div>
                                          </td>
                                          <td className="text-center py-3">
                                            <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                                              {asset.exchange || '-'}
                                            </span>
                                          </td>
                                          <td className="text-center py-3">{asset.total_bought.toFixed(asset.total_bought < 1 ? 8 : 2)}</td>
                                          <td className="text-center py-3">{formatCurrency(asset.total_bought_value)}</td>
                                          <td className="text-center py-3">{asset.total_sold.toFixed(asset.total_sold < 1 ? 8 : 2)}</td>
                                          <td className="text-center py-3">{formatCurrency(asset.total_sold_value)}</td>
                                          <td className={`text-center py-3 ${asset.realized_gain >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                            {asset.realized_gain >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(asset.realized_gain)}
                                          </td>
                                        </tr>
                                      )
                                    }

                                    return (
                                      <Fragment key={group.symbol}>
                                        <tr
                                          className="border-b cursor-pointer hover:bg-muted/30 transition-colors"
                                          onClick={() => toggleHistoryExpanded(group.symbol)}
                                        >
                                          <td className="py-3 text-center">
                                            <div className="flex justify-center">
                                              <AssetIconCompact symbol={group.symbol} name={group.name} assetType={group.asset_type} size={36} />
                                            </div>
                                          </td>
                                          <td className="text-center py-3">
                                            <div className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                                              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                                              <span>{group.assets.length} plateformes</span>
                                            </div>
                                          </td>
                                          <td className="text-center py-3 font-medium">{group.totalBought.toFixed(group.totalBought < 1 ? 8 : 2)}</td>
                                          <td className="text-center py-3 font-medium">{formatCurrency(group.totalBoughtValue)}</td>
                                          <td className="text-center py-3 font-medium">{group.totalSold.toFixed(group.totalSold < 1 ? 8 : 2)}</td>
                                          <td className="text-center py-3 font-medium">{formatCurrency(group.totalSoldValue)}</td>
                                          <td className={`text-center py-3 font-medium ${group.realizedGain >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                            {group.realizedGain >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(group.realizedGain)}
                                          </td>
                                        </tr>
                                        {isExpanded && group.assets.map((asset) => (
                                          <tr key={asset.id} className="border-b last:border-0 bg-muted/20">
                                            <td className="py-2 text-center" />
                                            <td className="text-center py-2">
                                              <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                                                {asset.exchange || '-'}
                                              </span>
                                            </td>
                                            <td className="text-center py-2 text-sm">{asset.total_bought.toFixed(asset.total_bought < 1 ? 8 : 2)}</td>
                                            <td className="text-center py-2 text-sm">{formatCurrency(asset.total_bought_value)}</td>
                                            <td className="text-center py-2 text-sm">{asset.total_sold.toFixed(asset.total_sold < 1 ? 8 : 2)}</td>
                                            <td className="text-center py-2 text-sm">{formatCurrency(asset.total_sold_value)}</td>
                                            <td className={`text-center py-2 text-sm ${asset.realized_gain >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                              {asset.realized_gain >= 0 ? '\u25B2' : '\u25BC'} {formatCurrency(asset.realized_gain)}
                                            </td>
                                          </tr>
                                        ))}
                                      </Fragment>
                                    )
                                  })
                              })()}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground">
                        Aucun actif vendu
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    Aucune donnée historique
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Dialogs */}
      <AddPortfolioForm open={showAddPortfolio} onOpenChange={setShowAddPortfolio} />

      {showAddAsset && (
        <AddAssetForm
          open={true}
          onOpenChange={() => setShowAddAsset(null)}
          portfolioId={showAddAsset.portfolioId}
          portfolioName={showAddAsset.portfolioName}
        />
      )}

      {showAddTransaction && (
        <AddTransactionForm
          open={true}
          onOpenChange={() => setShowAddTransaction(null)}
          assetId={showAddTransaction.assetId}
          assetSymbol={showAddTransaction.assetSymbol}
        />
      )}

      <ImportCSVForm
        open={showImportCSV}
        onOpenChange={setShowImportCSV}
        portfolioId={selectedPortfolio || undefined}
        onSuccess={() => {
          setShowImportCSV(false)
          invalidateAllFinancialData(queryClient)
        }}
      />

      {currentPortfolio && (
        <CashBalanceForm
          portfolioId={currentPortfolio.id}
          cashBalances={currentPortfolio.cash_balances || {}}
          open={showCashBalance}
          onOpenChange={setShowCashBalance}
        />
      )}

      {/* Delete Asset Confirmation */}
      <AlertDialog open={deleteAsset !== null} onOpenChange={(open) => !open && setDeleteAsset(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer cet actif ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteAsset && (
                <>
                  Voulez-vous vraiment supprimer <strong>{deleteAsset.symbol}</strong> ?
                  <br /><br />
                  <span className="text-destructive font-medium">
                    Toutes les transactions associées seront également supprimées.
                  </span>
                  <br />
                  Cette action est irréversible.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90"
              onClick={() => deleteAsset && deleteAssetMutation.mutate(deleteAsset.id)}
              disabled={deleteAssetMutation.isPending}
            >
              {deleteAssetMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Portfolio Confirmation */}
      <AlertDialog open={deletePortfolio !== null} onOpenChange={(open) => !open && setDeletePortfolio(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Supprimer ce portefeuille ?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deletePortfolio && (
                <>
                  Voulez-vous vraiment supprimer le portefeuille <strong>{deletePortfolio.name}</strong> ?
                  <br /><br />
                  <span className="text-destructive font-medium">
                    Tous les actifs et transactions associés seront également supprimés.
                  </span>
                  <br />
                  Cette action est irréversible.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90"
              onClick={() => deletePortfolio && deletePortfolioMutation.mutate(deletePortfolio.id)}
              disabled={deletePortfolioMutation.isPending}
            >
              {deletePortfolioMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
